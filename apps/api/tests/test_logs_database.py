"""Opt-in only, after approved 0002. Never creates tables or runs migrations."""

import hashlib
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import dotenv_values
from incidentiq.application.log_ingestion import ingest
from incidentiq.config import Settings
from incidentiq.domain.logs import LogBusy, records
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.log_models import EventRow, RunRow
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.log_source import manifest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.environ.get("INCIDENTIQ_RUN_LOG_DB_TESTS") != "1",
        reason="explicit post-migration opt-in required",
    ),
]


@pytest.fixture
def storage(tmp_path):
    path = Path(__file__).resolve().parents[1] / "api.env"
    settings = Settings(
        environment=dotenv_values(path).get("INCIDENTIQ_ENV", "development"),
        database_url=SecretStr(dotenv_values(path).get("DATABASE_URL") or ""),
    )
    assert settings.environment == "development" and settings.database_url is not None
    engine = database_engine(settings.database_url, pooled=False)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            revision = connection.scalar(
                text("SELECT version_num FROM public.incidentiq_alembic_version")
            )
            assert revision in {"0002_logs", "0003_retrieval"}, (
                "Apply the reviewed migration separately first"
            )
            # Commits release savepoints; the outer transaction rolls back all test rows.
            sessions = sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            payload = b"[Sun Jan 01 00:00:01 2006] [error] synthetic database test\n" * 20
            path = tmp_path / "synthetic.log"
            path.write_bytes(payload)
            source = replace(
                manifest(),
                sha256=hashlib.sha256(payload).hexdigest(),
                byte_count=len(payload),
                line_count=20,
            )
            yield PostgresLogRepository(sessions), path, source, connection
        finally:
            transaction.rollback()
    engine.dispose()


def test_postgres_ingestion_idempotency_and_read_filters(storage):
    repository, path, source, connection = storage
    first = ingest(repository, path, source, batch_size=10)
    second = ingest(repository, path, source, batch_size=10)
    assert first.inserted == 20 and second.duplicates == 20
    assert (
        connection.scalar(
            select(func.count()).select_from(EventRow).where(EventRow.file_id == source.file_id)
        )
        == 20
    )
    items = repository.read(
        "events", file_id=source.file_id, limit=10, level="error", q="synthetic"
    )
    assert len(items) == 10 and "raw_line" not in items[0]
    assert repository.read("events", file_id=source.file_id, q="%_") == []
    assert "raw_line" in repository.read("events", identity=items[0]["id"])[0]


def test_postgres_expiry_resume_and_stale_worker(storage):
    repository, path, source, connection = storage
    token = uuid4()
    run = repository.claim(source, token, None)
    with path.open("rb") as stream:
        batch = list(records(stream, source.file_id))[:10]
    repository.commit_batch(run.id, token, batch)
    with pytest.raises(LogBusy):
        repository.claim(source, uuid4(), None)
    # Synthetic expired lease, confined to this rolled-back test transaction.
    connection.execute(
        RunRow.__table__.update()
        .where(RunRow.id == run.id)
        .values(
            started_at=run.started_at - timedelta(seconds=120),
            heartbeat_at=run.heartbeat_at - timedelta(seconds=120),
            lease_expires_at=run.lease_expires_at - timedelta(seconds=120),
        )
    )
    newer = repository.claim(source, uuid4(), run.id)
    with pytest.raises(LogBusy):
        repository.commit_batch(run.id, token, batch)
    with path.open("rb") as stream:
        next_line = next(item for item in records(stream, source.file_id) if item.source_line == 11)
    repository.commit_batch(run.id, newer.owner_token, [next_line])
    assert repository.checkpoint(run.id, newer.owner_token).last_committed_line == 11


def test_postgres_two_connections_cannot_claim_workers(storage):
    repository, _, source, connection = storage
    repository.claim(source, uuid4(), None)
    # Outer rollback keeps the first transaction/claim lock alive. The independent
    # connection must fail immediately rather than enqueue another ingestion worker.
    other = PostgresLogRepository(sessionmaker(connection.engine, expire_on_commit=False))
    with pytest.raises(LogBusy):
        other.claim(source, uuid4(), None)
