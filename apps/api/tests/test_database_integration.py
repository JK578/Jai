"""Opt-in tests use outer transaction rollback; never delete or reset existing data."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from incidentiq.application.incidents import IncidentConflict
from incidentiq.config import Settings
from incidentiq.domain.incidents import Incident, Severity
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.postgres import PostgresIncidentRepository
from incidentiq.main import create_app
from pydantic import SecretStr
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("INCIDENTIQ_RUN_DB_TESTS") != "1", reason="Opt-in PostgreSQL tests"
    ),
]


@pytest.fixture
def sessions() -> Iterator[sessionmaker[Session]]:
    path = Path(__file__).resolve().parents[1] / "api.env"
    raw = os.getenv("DATABASE_TEST_URL") or dotenv_values(path).get("DATABASE_URL")
    if not raw:
        pytest.fail("Database integration URL is missing", pytrace=False)
    engine = database_engine(SecretStr(raw), pooled=False)
    try:
        connection = engine.connect()
    except Exception:
        engine.dispose()
        pytest.fail("Database integration connection failed; details suppressed", pytrace=False)
    transaction = connection.begin()
    try:
        if not inspect(connection).has_table("incidents", schema="incidentiq"):
            pytest.fail("Apply the reviewed migration first", pytrace=False)
        yield sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_postgres_repository_roundtrip_ordering_and_rollback(
    sessions: sessionmaker[Session],
) -> None:
    repository = PostgresIncidentRepository(sessions)
    first = Incident.create("Integration first", "Rollback-only fixture", Severity.LOW, "test-api")
    second = Incident.create(
        "Integration second", "Rollback-only fixture", Severity.HIGH, "test-api"
    )
    repository.add(first)
    repository.add(second)
    assert repository.get(first.id) == first
    identifiers = [item.id for item in repository.list()]
    assert identifiers.index(second.id) < identifiers.index(first.id)
    with pytest.raises(IncidentConflict):
        repository.add(first)
    assert repository.get(second.id) == second  # Failed write rolled back; sessions remain usable.


def test_postgres_api_roundtrip_across_application_instances(
    sessions: sessionmaker[Session],
) -> None:
    repository = PostgresIncidentRepository(sessions)
    with TestClient(create_app(Settings(environment="test"), repository)) as client:
        response = client.post(
            "/api/v1/incidents",
            json={
                "title": "Integration API",
                "description": "Rollback-only fixture",
                "severity": "critical",
                "service_name": "test-api",
            },
        )
        assert response.status_code == 201
        incident = response.json()
        assert client.get(f"/api/v1/incidents/{incident['id']}").json() == incident
    with TestClient(
        create_app(Settings(environment="test"), PostgresIncidentRepository(sessions))
    ) as client:
        assert client.get(f"/api/v1/incidents/{incident['id']}").json() == incident
        assert incident in client.get("/api/v1/incidents").json()
