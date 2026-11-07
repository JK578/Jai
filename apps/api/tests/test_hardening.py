from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from incidentiq.config import Settings
from incidentiq.domain.access import AccessDenied
from incidentiq.infrastructure.usage_budget import UsageBudget
from incidentiq.main import create_app


def test_atomic_daily_budget_prevents_concurrent_overspend(tmp_path):
    budget = UsageBudget(tmp_path / "usage.sqlite", limit=100)

    def reserve(_):
        try:
            budget.reserve("user", 20)
            return True
        except AccessDenied:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(20))) == 5
    assert budget.reserve("other-user", 100) == 0
    with pytest.raises(AccessDenied):
        UsageBudget(tmp_path / "usage.sqlite", limit=100).reserve("user", 1)


def test_oversized_api_body_and_untrusted_host_rejected():
    with TestClient(create_app(Settings(storage="memory"))) as client:
        response = client.post("/api/v1/incidents", content=b"x" * 65537)
        assert response.status_code == 413
        assert client.get("/health/live", headers={"host": "evil.example"}).status_code == 400


def test_request_logs_exclude_credentials_queries_bodies_and_unknown_paths(caplog):
    secret = "must-not-appear-in-request-logs"
    with TestClient(create_app(Settings(storage="memory"))) as client:
        client.get(f"/unknown/{secret}?token={secret}", headers={"Authorization": secret})
        client.post("/api/v1/incidents", json={"title": secret})
    events = [row.message for row in caplog.records if row.name == "incidentiq"]
    assert events and all(secret not in event for event in events)
    assert any('"path": "/unmatched"' in event for event in events)
