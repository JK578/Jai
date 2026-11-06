"""Post-approval integration tests; outer rollback preserves all pre-existing data."""

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import dotenv_values
from incidentiq.application.log_ingestion import ingest
from incidentiq.config import Settings
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.log_source import manifest
from incidentiq.infrastructure.retrieval_postgres import PostgresRetrievalIndex
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("INCIDENTIQ_RUN_RETRIEVAL_DB_TESTS") != "1",
        reason="explicit post-migration retrieval test opt-in required",
    ),
]


@pytest.fixture
def storage(tmp_path):
    values = dotenv_values(Path(__file__).resolve().parents[1] / "api.env")
    settings = Settings(
        environment=values.get("INCIDENTIQ_ENV", "development"),
        database_url=SecretStr(values.get("DATABASE_URL") or ""),
    )
    assert settings.environment == "development" and settings.database_url is not None
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.connect() as connection:
            outer = connection.begin()
            try:
                assert (
                    connection.scalar(
                        text("SELECT version_num FROM public.incidentiq_alembic_version")
                    )
                    == "0003_retrieval"
                )
                sessions = sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                payload = b"[Sun Jan 01 00:00:01 2006] [error] synthetic restart event\n" * 20
                path = tmp_path / "retrieval.log"
                path.write_bytes(payload)
                source = replace(
                    manifest(),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    byte_count=len(payload),
                    line_count=20,
                )
                ingest(PostgresLogRepository(sessions), path, source, batch_size=10)
                yield PostgresRetrievalIndex(sessions), source.file_id, connection
            finally:
                outer.rollback()
    finally:
        engine.dispose()


def test_real_pgvector_publication_search_replay_delete(storage):
    index, file_id, connection = storage
    evidence = index.load_file(file_id)
    vector = (1.0,) + (0.0,) * 511
    index.replace_file(file_id, evidence, [vector] * 20, "fixture-512", 512)
    assert index.matches_file(file_id, evidence, "fixture-512", 512)
    assert not index.matches_file(file_id, evidence, "different-model", 512)
    hits = index.search(file_id, "synthetic restart", vector, "fixture-512", 512, 5)
    assert len(hits) == 5
    assert all(hit.keyword_rank is not None and hit.vector_rank is not None for hit in hits)
    assert all(hit.evidence in evidence for hit in hits)
    for mode in ("keyword", "vector"):
        branch = index.search(
            file_id, "synthetic restart", vector, "fixture-512", 512, 5, mode=mode
        )
        assert len(branch) == 5 and all(hit.evidence in evidence for hit in branch)
    index.replace_file(file_id, evidence, [vector] * 20, "fixture-512", 512)
    assert index.search(file_id, "synthetic restart", vector, "fixture-512", 512, 5) == hits
    assert (
        connection.scalar(
            text("SELECT count(*) FROM incidentiq.retrieval_documents WHERE file_id=:id"),
            {"id": file_id},
        )
        == 20
    )
    assert index.delete_file(file_id) == 20
    assert index.search(file_id, "synthetic restart", vector, "fixture-512", 512, 5) == []
    assert (
        connection.scalar(
            text("SELECT count(*) FROM incidentiq.log_events WHERE file_id=:id"), {"id": file_id}
        )
        == 20
    )
