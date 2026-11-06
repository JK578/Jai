"""Transactional fault-injection fake. Does not substitute for PostgreSQL verification."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from incidentiq.domain.logs import (
    LEASE_SECONDS,
    DatasetManifest,
    IngestionRun,
    LogBusy,
    LogError,
    LogTransient,
    ParsedLine,
    advance,
    require_owner,
)


class FakeLogRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, IngestionRun] = {}
        self.events = {}
        self.errors = {}
        self.now = datetime.now(UTC)
        self.lock = RLock()
        self.fault: str | None = None
        self.maximum_batch = 0

    def claim(self, source: DatasetManifest, token: UUID, resume: UUID | None) -> IngestionRun:
        with self.lock:
            active = next((r for r in self.runs.values() if r.state == "running"), None)
            if active and (active.id != resume or active.lease_expires_at > self.now):
                raise LogBusy("worker_already_active")
            if resume:
                run = self.runs[resume]
                if run.file_id != source.file_id or run.state not in {"running", "failed"}:
                    raise LogError("resume_source_mismatch")
                run.state, run.owner_token = "running", token
                run.heartbeat_at = self.now
                run.lease_expires_at = self.now + timedelta(seconds=LEASE_SECONDS)
                run.finished_at, run.failure_code = None, None
            else:
                run = IngestionRun(
                    uuid4(),
                    source.file_id,
                    source.parser_version,
                    "running",
                    0,
                    0,
                    0,
                    0,
                    0,
                    self.now,
                    self.now,
                    self.now + timedelta(seconds=LEASE_SECONDS),
                    token,
                )
                self.runs[run.id] = run
            return deepcopy(run)

    def checkpoint(self, run_id: UUID, token: UUID) -> IngestionRun:
        require_owner(self.runs[run_id], token, self.now)
        return deepcopy(self.runs[run_id])

    def commit_batch(self, run_id: UUID, token: UUID, batch: list[ParsedLine]) -> None:
        with self.lock:
            run, events, errors = deepcopy((self.runs[run_id], self.events, self.errors))
            self.maximum_batch = max(self.maximum_batch, sum(i.size for i in batch))
            inserted = 0
            for item in batch:
                if item.event:
                    if item.event.id in events:
                        if events[item.event.id].raw_line_sha256 != item.digest:
                            raise LogError("event_digest_conflict")
                    else:
                        events[item.event.id] = item.event
                        inserted += 1
                elif sum(k[0] == run_id for k in errors) < 100:
                    errors[(run_id, item.source_line)] = item.error_code
            if not advance(run, token, batch, inserted, self.now):
                return
            fault, self.fault = self.fault, None
            if fault == "before_commit":
                raise LogTransient("simulated_disconnect")
            if fault == "crash":
                raise SystemExit("simulated_process_death")
            self.runs[run_id], self.events, self.errors = run, events, errors
            if fault == "after_commit":
                raise LogTransient("simulated_lost_acknowledgement")

    def finish(self, run_id: UUID, token: UUID, expected_lines: int) -> IngestionRun:
        run = self.runs[run_id]
        require_owner(run, token, self.now)
        if run.processed != expected_lines:
            raise LogError("source_line_count_mismatch")
        run.state, run.finished_at = ("partial" if run.rejected else "completed"), self.now
        return deepcopy(run)

    def fail(self, run_id: UUID, token: UUID) -> None:
        run = self.runs[run_id]
        require_owner(run, token, self.now)
        run.state, run.finished_at = "failed", self.now
