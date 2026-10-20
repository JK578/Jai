from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from incidentiq.application.incidents import IncidentNotFound, IncidentService
from incidentiq.config import Settings
from incidentiq.domain.incidents import Incident, IncidentStatus, Severity
from incidentiq.infrastructure.memory import InMemoryIncidentRepository
from incidentiq.main import create_app

PAYLOAD = {
    "title": " Checkout unavailable ",
    "description": " Elevated HTTP 503 responses ",
    "severity": "high",
    "service_name": " checkout-api ",
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(environment="test"))) as client:
        yield client


def test_domain_creation_invariants() -> None:
    item = Incident.create(" title ", " description ", Severity.HIGH, " service ")
    assert isinstance(item.id, UUID)
    assert item.title == "title"
    assert item.description == "description"
    assert item.service_name == "service"
    assert item.status is IncidentStatus.OPEN
    assert item.created_at == item.updated_at
    assert item.created_at.tzinfo is UTC
    assert Incident.create("title", "description", Severity.LOW, "service").id != item.id
    with pytest.raises(FrozenInstanceError):
        item.title = "changed"
    with pytest.raises(ValueError):
        replace(item, title=" ")
    with pytest.raises(ValueError):
        replace(item, updated_at=item.created_at - timedelta(seconds=1))
    with pytest.raises(ValueError):
        replace(item, created_at=datetime(2026, 1, 1))


def test_service_and_memory_repository_contract() -> None:
    repository = InMemoryIncidentRepository()
    service = IncidentService(repository)
    assert service.list() == []
    first = service.create("First", "Description", Severity.LOW, "api")
    second = service.create("Second", "Description", Severity.CRITICAL, "api")
    assert service.list() == [second, first]
    assert service.get(first.id) == first
    snapshot = service.list()
    snapshot.clear()
    assert len(service.list()) == 2
    with pytest.raises(ValueError):
        repository.add(first)
    with pytest.raises(IncidentNotFound):
        service.get(uuid4())
    assert InMemoryIncidentRepository().list() == []


def test_create_list_detail_and_health(client: TestClient) -> None:
    assert client.get("/api/v1/incidents").json() == []
    response = client.post("/api/v1/incidents", json=PAYLOAD)
    assert response.status_code == 201
    item = response.json()
    UUID(item["id"])
    assert item["title"] == "Checkout unavailable"
    assert item["description"] == "Elevated HTTP 503 responses"
    assert item["service_name"] == "checkout-api"
    assert item["severity"] == "high" and item["status"] == "open"
    assert item["created_at"] == item["updated_at"]
    assert datetime.fromisoformat(item["created_at"]).utcoffset() == timedelta(0)
    assert response.headers["location"] == f"/api/v1/incidents/{item['id']}"
    assert client.get(response.headers["location"]).json() == item
    listed = client.get("/api/v1/incidents")
    assert listed.json() == [item]
    assert listed.headers["cache-control"] == "no-store"
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_severity_values(client: TestClient, severity: str) -> None:
    response = client.post("/api/v1/incidents", json={**PAYLOAD, "severity": severity})
    assert response.status_code == 201
    assert response.json()["severity"] == severity


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"description": "\n"},
        {"service_name": "\t"},
        {"title": "x" * 201},
        {"description": "x" * 10001},
        {"service_name": "x" * 101},
        {"severity": "urgent"},
        {"title": 123},
        {"description": None},
        {"status": "resolved"},
        {"id": str(uuid4())},
        {"created_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_creation_is_rejected_without_writes(
    client: TestClient,
    changes: dict[str, object],
) -> None:
    assert client.post("/api/v1/incidents", json={**PAYLOAD, **changes}).status_code == 422
    assert client.get("/api/v1/incidents").json() == []


def test_defaults_missing_fields_and_malformed_json(client: TestClient) -> None:
    payload = {key: value for key, value in PAYLOAD.items() if key != "severity"}
    assert client.post("/api/v1/incidents", json=payload).json()["severity"] == "medium"
    assert client.post("/api/v1/incidents", json={}).status_code == 422
    assert (
        client.post(
            "/api/v1/incidents", content="{", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )


def test_unknown_and_invalid_id(client: TestClient) -> None:
    response = client.get(f"/api/v1/incidents/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}
    assert client.get("/api/v1/incidents/not-a-uuid").status_code == 422


def test_apps_do_not_share_incidents(client: TestClient) -> None:
    client.post("/api/v1/incidents", json=PAYLOAD)
    with TestClient(create_app(Settings(environment="test"))) as fresh:
        assert fresh.get("/api/v1/incidents").json() == []
