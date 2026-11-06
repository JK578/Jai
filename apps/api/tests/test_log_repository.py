"""Offline adapter contract checks; SQL compilation is PostgreSQL-specific."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from incidentiq.domain.logs import IngestionRun, LogBusy, LogError, LogTransient, parse_line
from incidentiq.infrastructure.log_models import RunRow
from incidentiq.infrastructure.log_repository import PostgresLogRepository, safe_database
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError


def setup_batch():
    now = datetime.now(UTC)
    token, run_id, file_id = uuid4(), uuid4(), uuid4()
    run = IngestionRun(
        run_id,
        file_id,
        "apache-error-v1",
        "running",
        0,
        0,
        0,
        0,
        0,
        now,
        now,
        now + timedelta(seconds=60),
        token,
    )
    row = RunRow(**asdict(run))
    item = parse_line(b"[Sun Jan 01 00:00:01 2006] [error] synthetic adapter test", file_id, 1)
    factory = MagicMock()
    session = factory.begin.return_value.__enter__.return_value
    session.scalar.side_effect = [row, now, now]
    session.scalars.return_value.all.return_value = [item.event.id]
    session.execute.return_value.all.return_value = [(1, item.event.id, item.digest)]
    return PostgresLogRepository(factory), factory, session, row, token, item


def test_postgres_batch_atomic_session_and_counts():
    repository, factory, session, row, token, item = setup_batch()
    repository.commit_batch(row.id, token, [item])
    assert (row.processed, row.inserted, row.duplicates, row.last_committed_line) == (1, 1, 0, 1)
    factory.begin.return_value.__exit__.assert_called_once_with(None, None, None)
    statement = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (file_id, source_line) DO NOTHING" in str(statement)
    assert item.event.message not in str(statement)  # Parameterized values.


def test_postgres_digest_conflict_rolls_back_checkpoint():
    repository, factory, session, row, token, item = setup_batch()
    session.execute.return_value.all.return_value = [(1, item.event.id, b"x" * 32)]
    with pytest.raises(LogError, match="event_digest_conflict"):
        repository.commit_batch(row.id, token, [item])
    assert row.processed == 0
    assert factory.begin.return_value.__exit__.call_args.args[0] is LogError


def test_postgres_stale_token_never_inserts():
    repository, _, session, row, _, item = setup_batch()
    with pytest.raises(LogBusy):
        repository.commit_batch(row.id, uuid4(), [item])
    session.scalars.assert_not_called()
    assert row.processed == 0


def test_postgres_insert_error_rolls_back_and_sanitizes():
    repository, factory, session, row, token, item = setup_batch()
    session.scalars.side_effect = IntegrityError("private SQL", {}, Exception("fake secret"))
    with pytest.raises(LogBusy, match="ingestion_conflict"):
        repository.commit_batch(row.id, token, [item])
    assert row.processed == 0
    assert factory.begin.return_value.__exit__.call_args.args[0] is IntegrityError


def test_transient_disconnect_classification():
    @safe_database
    def fail():
        raise DBAPIError("private SQL", {}, Exception("private data"), connection_invalidated=True)

    with pytest.raises(LogTransient, match="storage_temporarily_unavailable"):
        fail()


def test_parameterized_literal_substring_read_and_bounds():
    factory = MagicMock()
    session = factory.return_value.__enter__.return_value
    session.scalars.return_value = []
    PostgresLogRepository(factory).read("events", file_id=uuid4(), q="%_'; SELECT private")
    statement = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "SELECT private" not in str(statement)
    assert any("/%/_" in str(value) for value in statement.params.values())
    with pytest.raises(LogError, match="invalid_read_bounds"):
        PostgresLogRepository(factory).read("events", limit=100000)


def test_run_read_hides_ownership_and_reports_expiry_without_writing():
    repository, factory, _, row, _, _ = setup_batch()
    session = factory.return_value.__enter__.return_value
    session.scalar.return_value = row.lease_expires_at + timedelta(seconds=1)
    session.scalars.return_value = [row]
    item = repository.read("runs")[0]
    assert "owner_token" not in item and item["state"] == "interrupted"
    assert row.state == "running"
    session.add.assert_not_called()
