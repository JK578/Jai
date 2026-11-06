"""PostgreSQL ingestion transactions and bounded read queries."""

import json
from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from functools import wraps
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from incidentiq.domain.logs import (
    LEASE_SECONDS,
    MAX_ERRORS,
    DatasetManifest,
    IngestionRun,
    LogBusy,
    LogError,
    LogTransient,
    LogUnavailable,
    ParsedLine,
    advance,
    require_owner,
)
from incidentiq.infrastructure.database import Database
from incidentiq.infrastructure.log_models import DatasetRow, ErrorRow, EventRow, FileRow, RunRow


def safe_database(function: Callable) -> Callable:
    @wraps(function)
    def protected(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except IntegrityError:
            raise LogBusy("ingestion_conflict") from None
        except DBAPIError as error:
            code = getattr(error.orig, "sqlstate", "") or ""
            if error.connection_invalidated or code in {"40001", "40P01"} or code.startswith("08"):
                raise LogTransient("storage_temporarily_unavailable") from None
            raise LogUnavailable("log_storage_unavailable") from None
        except SQLAlchemyError:
            raise LogUnavailable("log_storage_unavailable") from None

    return protected


def run_domain(row: RunRow) -> IngestionRun:
    return IngestionRun(**{field.name: getattr(row, field.name) for field in fields(IngestionRun)})


def update_run(row: RunRow, run: IngestionRun) -> None:
    for field in fields(IngestionRun):
        setattr(row, field.name, getattr(run, field.name))


def locked(session: Session, run_id: UUID, token: UUID) -> tuple[RunRow, IngestionRun, datetime]:
    row = session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
    if row is None:
        raise LogError("run_not_found")
    now = session.scalar(select(func.clock_timestamp()))
    run = run_domain(row)
    require_owner(run, token, now)
    return row, run, now


class PostgresLogRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    @safe_database
    def claim(self, source: DatasetManifest, token: UUID, resume: UUID | None) -> IngestionRun:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            session.execute(text("SET LOCAL lock_timeout = '2000ms'"))
            # Transaction-scoped serialization works with transaction poolers.
            if not session.scalar(text("SELECT pg_try_advisory_xact_lock(1938462)")):
                raise LogBusy("worker_already_active")
            if (
                session.scalar(select(func.pg_database_size(func.current_database())))
                > 400 * 1024**2
            ):
                raise LogError("database_storage_budget_exceeded")
            now = session.scalar(select(func.clock_timestamp()))
            if session.scalar(select(func.count()).select_from(RunRow)) >= 50 and resume is None:
                raise LogError("ingestion_audit_budget_exceeded")
            active = session.scalar(
                select(RunRow).where(RunRow.state == "running").with_for_update()
            )
            if active is not None and (active.id != resume or active.lease_expires_at > now):
                raise LogBusy("worker_active_or_expired_resume_required")
            if resume is not None:
                row = session.scalar(select(RunRow).where(RunRow.id == resume).with_for_update())
                if (
                    row is None
                    or row.file_id != source.file_id
                    or row.parser_version != source.parser_version
                ):
                    raise LogError("resume_source_mismatch")
                if row.state not in {"running", "failed"}:
                    raise LogError("run_not_resumable")
                if row.state == "running" and row.lease_expires_at > now:
                    raise LogBusy("worker_already_active")
                row.owner_token, row.state = token, "running"
                row.heartbeat_at, row.lease_expires_at = now, now + timedelta(seconds=LEASE_SECONDS)
                row.finished_at, row.failure_code = None, None
            else:
                session.execute(
                    insert(DatasetRow)
                    .values(
                        id=source.dataset_id,
                        slug=source.slug,
                        manifest_json=json.dumps(asdict(source)),
                    )
                    .on_conflict_do_nothing(index_elements=[DatasetRow.id])
                )
                session.execute(
                    insert(FileRow)
                    .values(
                        id=source.file_id,
                        dataset_id=source.dataset_id,
                        sha256=source.sha256,
                        byte_count=source.byte_count,
                        line_count=source.line_count,
                        parser_version=source.parser_version,
                        source_path=source.source_path,
                        source_commit=source.commit,
                    )
                    .on_conflict_do_nothing(index_elements=[FileRow.id])
                )
                session.flush()
                stored = session.get(FileRow, source.file_id)
                if (
                    stored is None
                    or any(
                        getattr(stored, name) != getattr(source, name)
                        for name in (
                            "parser_version",
                            "sha256",
                            "byte_count",
                            "line_count",
                            "source_path",
                        )
                    )
                    or (stored.source_commit != source.commit)
                ):
                    raise LogError("immutable_file_conflict")
                row = RunRow(
                    id=uuid4(),
                    file_id=source.file_id,
                    parser_version=source.parser_version,
                    state="running",
                    processed=0,
                    inserted=0,
                    duplicates=0,
                    rejected=0,
                    last_committed_line=0,
                    started_at=now,
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                    owner_token=token,
                )
                session.add(row)
            session.flush()
            return run_domain(row)

    @safe_database
    def checkpoint(self, run_id: UUID, token: UUID) -> IngestionRun:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            _, run, _ = locked(session, run_id, token)
            return run

    @safe_database
    def commit_batch(self, run_id: UUID, token: UUID, batch: list[ParsedLine]) -> None:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            session.execute(text("SET LOCAL lock_timeout = '2000ms'"))
            row, run, now = locked(session, run_id, token)
            # Validate bounds before writes; any conflict rolls back the transaction.
            if not advance(run, token, batch, 0, now):
                return
            events = [item.event for item in batch if item.event is not None]
            if any(event.file_id != run.file_id for event in events):
                raise LogError("batch_file_mismatch")
            inserted = 0
            if events:
                inserted = len(
                    session.scalars(
                        insert(EventRow)
                        .values([asdict(event) for event in events])
                        .on_conflict_do_nothing(
                            index_elements=[EventRow.file_id, EventRow.source_line]
                        )
                        .returning(EventRow.id)
                    ).all()
                )
                stored = {
                    line: (identity, digest)
                    for line, identity, digest in session.execute(
                        select(EventRow.source_line, EventRow.id, EventRow.raw_line_sha256).where(
                            EventRow.file_id == run.file_id,
                            EventRow.source_line.in_([event.source_line for event in events]),
                        )
                    ).all()
                }
                if any(
                    stored.get(event.source_line) != (event.id, event.raw_line_sha256)
                    for event in events
                ):
                    raise LogError("event_digest_conflict")
            # Recompute from original checkpoint with actual inserted count.
            run = run_domain(row)
            advance(run, token, batch, inserted, now)
            sample = min(run.rejected - sum(item.event is None for item in batch), MAX_ERRORS)
            for item in batch:
                if item.event is None and sample < MAX_ERRORS:
                    sample += 1
                    session.add(
                        ErrorRow(
                            run_id=run.id,
                            source_line=item.source_line,
                            sample_number=sample,
                            error_code=item.error_code,
                            raw_line_sha256=item.digest,
                        )
                    )
            update_run(row, run)
            # Lease is checked again after SQL work using the database clock.
            require_owner(run_domain(row), token, session.scalar(select(func.clock_timestamp())))

    @safe_database
    def finish(self, run_id: UUID, token: UUID, expected_lines: int) -> IngestionRun:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            row, run, now = locked(session, run_id, token)
            if run.last_committed_line != expected_lines:
                raise LogError("source_line_count_mismatch")
            run.state, run.finished_at = ("partial" if run.rejected else "completed"), now
            update_run(row, run)
            return run

    @safe_database
    def fail(self, run_id: UUID, token: UUID) -> None:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            row, run, now = locked(session, run_id, token)
            row.state, row.finished_at, row.failure_code = "failed", now, "worker_failed"

    @safe_database
    def read(
        self,
        resource: str,
        *,
        identity: UUID | None = None,
        file_id: UUID | None = None,
        after: int = 0,
        limit: int = 50,
        level: str | None = None,
        q: str | None = None,
        from_local: datetime | None = None,
        to_local: datetime | None = None,
        state: str | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 101 or not 0 <= after <= 2000 or not 0 <= offset <= 10000:
            raise LogError("invalid_read_bounds")
        models = {"files": FileRow, "runs": RunRow, "errors": ErrorRow, "events": EventRow}
        model = models[resource]
        query = select(model)
        if resource == "events":
            if identity:
                query = query.where(EventRow.id == identity)
            else:
                query = query.where(EventRow.file_id == file_id, EventRow.source_line > after)
            if level:
                query = query.where(EventRow.normalized_level == level)
            if q:
                query = query.where(EventRow.message.contains(q, autoescape=True))
            if from_local:
                query = query.where(EventRow.event_time_local >= from_local)
            if to_local:
                query = query.where(EventRow.event_time_local <= to_local)
            query = query.order_by(EventRow.source_line)
        elif resource == "errors":
            query = query.where(ErrorRow.run_id == identity, ErrorRow.source_line > after)
            query = query.order_by(ErrorRow.source_line)
        elif resource == "runs":
            if identity:
                query = query.where(RunRow.id == identity)
            if file_id:
                query = query.where(RunRow.file_id == file_id)
            if state == "interrupted":
                query = query.where(
                    RunRow.state == "running", RunRow.lease_expires_at <= func.clock_timestamp()
                )
            elif state:
                query = query.where(RunRow.state == state)
                if state == "running":
                    query = query.where(RunRow.lease_expires_at > func.clock_timestamp())
            query = query.order_by(RunRow.started_at.desc(), RunRow.id.desc()).offset(offset)
        else:
            query = query.order_by(FileRow.id)
        with self.sessions() as session:
            Database.bound_statement(session)
            now = session.scalar(select(func.clock_timestamp()))
            result = []
            for row in session.scalars(query.limit(limit)):
                item = {
                    column.name: getattr(row, column.name)
                    for column in model.__table__.columns
                    if column.name != "owner_token"
                }
                if isinstance(row, RunRow):
                    item["state"] = run_domain(row).public_state(now)
                if isinstance(row, EventRow) and identity is None:
                    item.pop("raw_line")
                if isinstance(item.get("raw_line_sha256"), bytes):
                    item["raw_line_sha256"] = item["raw_line_sha256"].hex()
                result.append(item)
            return result
