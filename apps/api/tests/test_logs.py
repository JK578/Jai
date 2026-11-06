import hashlib
import io
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from incidentiq.application.log_ingestion import ingest
from incidentiq.application.log_source import verified_stream
from incidentiq.config import Settings
from incidentiq.domain.logs import (
    MAX_BATCH_BYTES,
    MAX_LINE_BYTES,
    LogBusy,
    LogError,
    LogUnavailable,
    advance,
    parse_line,
    records,
    verify_source,
)
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.log_source import manifest
from incidentiq.main import create_app
from log_fake import FakeLogRepository
from sqlalchemy.exc import SQLAlchemyError

SYNTHETIC = b"[Sun Jan 01 00:00:01 2006] [error] synthetic test message"


def fixture(tmp_path: Path, count: int = 40, invalid: int = 0):
    payload = (SYNTHETIC + b"\n") * (count - invalid) + b"invalid synthetic row\n" * invalid
    path = tmp_path / "synthetic.log"
    path.write_bytes(payload)
    source = replace(
        manifest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        line_count=count,
    )
    return path, source


def test_parser_identity_and_unknown_zone():
    file_id = uuid4()
    a, b = parse_line(SYNTHETIC, file_id, 1), parse_line(SYNTHETIC, file_id, 2)
    assert a.event.id != b.event.id
    assert a.event.id == parse_line(SYNTHETIC, file_id, 1).event.id
    assert a.event.event_time_local.tzinfo is None
    assert a.event.event_time_utc is None
    assert a.event.source_time_text == "Sun Jan 01 00:00:01 2006"
    assert a.event.raw_line == SYNTHETIC.decode()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"\xff", "invalid_encoding"),
        (b"x\x00", "nul_character"),
        (b"unstructured", "invalid_envelope"),
        (SYNTHETIC.replace(b"error", b"unknown"), "unsupported_level"),
        (SYNTHETIC.replace(b"Jan 01", b"Jan 99"), "invalid_timestamp"),
        (b"x" * (MAX_LINE_BYTES + 1), "line_too_long"),
    ],
)
def test_parser_rejections(payload, code):
    assert parse_line(payload, uuid4(), 1).error_code == code


def test_streaming_drains_long_line_and_preserves_line_numbers():
    items = list(records(io.BytesIO(b"x" * 100000 + b"\n" + SYNTHETIC + b"\r\n"), uuid4()))
    assert len(items) == 2
    assert items[0].error_code == "line_too_long"
    assert items[1].source_line == 2 and items[1].event is not None


def test_source_checksum_precedes_any_database_access(tmp_path):
    path, source = fixture(tmp_path)
    path.write_bytes(b"changed")
    repository = MagicMock()
    with pytest.raises(LogError):
        ingest(repository, path, source)
    repository.claim.assert_not_called()


def test_snapshot_is_private_and_verified(tmp_path):
    path, source = fixture(tmp_path)
    verify_source(path, source)
    with verified_stream(path, source) as stream:
        path.write_bytes(b"changed cache")
        assert len(list(records(stream, source.file_id))) == 40


@pytest.mark.parametrize("fault", [None, "before_commit", "after_commit"])
def test_ingestion_retry_and_repeat_idempotency(tmp_path, fault):
    path, source = fixture(tmp_path)
    repository = FakeLogRepository()
    repository.fault = fault
    result = ingest(repository, path, source, batch_size=10)
    assert (result.processed, result.inserted, result.duplicates, result.rejected) == (40, 40, 0, 0)
    repeated = ingest(repository, path, source, batch_size=10)
    assert (repeated.inserted, repeated.duplicates, len(repository.events)) == (0, 40, 40)
    assert repository.maximum_batch <= MAX_BATCH_BYTES


def test_process_death_expired_resume_and_stale_fencing(tmp_path):
    path, source = fixture(tmp_path)
    repository = FakeLogRepository()
    first_token = uuid4()
    run = repository.claim(source, first_token, None)
    repository.commit_batch(
        run.id, first_token, list(records(io.BytesIO((SYNTHETIC + b"\n") * 10), source.file_id))
    )
    with pytest.raises(LogBusy):
        ingest(repository, path, source, resume=run.id)
    repository.now += timedelta(seconds=61)
    assert repository.runs[run.id].public_state(repository.now) == "interrupted"
    result = ingest(repository, path, source, resume=run.id, batch_size=10)
    assert result.inserted == 40 and len(repository.events) == 40
    with pytest.raises(LogBusy):
        repository.fail(run.id, first_token)


def test_crash_before_commit_rolls_back_and_resumes(tmp_path):
    path, source = fixture(tmp_path)
    repository = FakeLogRepository()
    repository.fault = "crash"
    with pytest.raises(SystemExit):
        ingest(repository, path, source, batch_size=10)
    run = next(iter(repository.runs.values()))
    assert run.processed == 0 and not repository.events
    repository.now += timedelta(seconds=61)
    result = ingest(repository, path, source, resume=run.id)
    assert result.inserted == 40


def test_bounded_diagnostics_full_rejection_counts(tmp_path):
    path, source = fixture(tmp_path, 300, 200)
    repository = FakeLogRepository()
    result = ingest(repository, path, source)
    assert result.state == "partial" and result.rejected == 200
    assert len(repository.errors) == 100
    assert result.processed == result.inserted + result.duplicates + result.rejected == 300


def test_checkpoint_order_and_batch_bounds(tmp_path):
    _, source = fixture(tmp_path)
    repository = FakeLogRepository()
    token = uuid4()
    run = repository.claim(source, token, None)
    with pytest.raises(LogError, match="checkpoint_conflict"):
        advance(run, token, [parse_line(SYNTHETIC, source.file_id, 2)], 1, repository.now)
    with pytest.raises(LogError, match="invalid_batch"):
        advance(run, token, [], 0, repository.now)


def test_repository_errors_are_sanitized():
    factory = MagicMock()
    factory.begin.return_value.__enter__.side_effect = SQLAlchemyError("private fake credentials")
    with pytest.raises(LogUnavailable) as error:
        PostgresLogRepository(factory).claim(manifest(), uuid4(), None)
    assert str(error.value) == "log_storage_unavailable"


def test_log_http_validation_pagination_and_safe_failure():
    reader = MagicMock()
    reader.read.return_value = [{"source_line": 1}, {"source_line": 2}]
    with TestClient(create_app(Settings(environment="test"), log_repository=reader)) as client:
        url = f"/api/v1/logs?file_id={uuid4()}"
        assert client.get(url + "&limit=1").json()["next_cursor"] == 1
        assert client.get(url + "&limit=101").status_code == 422
        assert client.get(url + "&from_local=2006-01-01T00:00:00Z").status_code == 422
        assert client.get(url + "&level=unknown").status_code == 422
        assert client.get(url + "&q=" + "x" * 201).status_code == 422
        assert client.get("/api/v1/logs").status_code == 422
        reader.read.return_value = []
        assert client.get(f"/api/v1/logs/{uuid4()}").status_code == 404
        reader.read.side_effect = LogUnavailable("private data")
        response = client.get(url)
        assert response.status_code == 503 and "private" not in response.text
        assert client.get("/health/live").status_code == 200


def test_logs_are_unavailable_without_postgres():
    with TestClient(create_app(Settings(environment="test", storage="memory"))) as client:
        assert client.get("/api/v1/log-datasets").status_code == 503


def test_full_2000_line_synthetic_artifact(tmp_path):
    path, source = fixture(tmp_path, 2000)
    repository = FakeLogRepository()
    result = ingest(repository, path, source)
    assert result.processed == result.inserted == len(repository.events) == 2000
    assert result.state == "completed" and repository.maximum_batch <= MAX_BATCH_BYTES


def test_exact_line_limit_with_crlf_is_accepted():
    payload = SYNTHETIC + b"x" * (MAX_LINE_BYTES - len(SYNTHETIC))
    items = list(records(io.BytesIO(payload + b"\r\n"), uuid4()))
    assert len(items) == 1 and items[0].event is not None


def test_retry_exhaustion_leaves_resumable_checkpoint(tmp_path, monkeypatch):
    from incidentiq.domain.logs import LogTransient

    path, source = fixture(tmp_path)
    repository = FakeLogRepository()
    calls = 0
    original = repository.commit_batch

    def unavailable(*_args):
        nonlocal calls
        calls += 1
        raise LogTransient("storage_temporarily_unavailable")

    monkeypatch.setattr(repository, "commit_batch", unavailable)
    with pytest.raises(LogTransient):
        ingest(repository, path, source)
    run = next(iter(repository.runs.values()))
    assert calls == 3 and run.processed == 0 and run.state == "failed"
    monkeypatch.setattr(repository, "commit_batch", original)
    assert ingest(repository, path, source, resume=run.id).inserted == 40


def test_stale_worker_cannot_mutate_successor_while_running(tmp_path):
    _, source = fixture(tmp_path)
    repository = FakeLogRepository()
    token = uuid4()
    first = repository.claim(source, token, None)
    repository.now += timedelta(seconds=61)
    newer = repository.claim(source, uuid4(), first.id)
    with pytest.raises(LogBusy):
        repository.commit_batch(first.id, token, [parse_line(SYNTHETIC, source.file_id, 1)])
    with pytest.raises(LogBusy):
        repository.fail(first.id, token)
    assert repository.runs[first.id].owner_token == newer.owner_token
    assert repository.runs[first.id].state == "running" and not repository.events
