import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from incidentiq.config import Settings, load_settings
from incidentiq.main import create_app
from pydantic import ValidationError


def test_health_contract_and_logging(caplog: pytest.LogCaptureFixture) -> None:
    with TestClient(create_app(Settings(environment="test"))) as client:
        assert client.get("/health/live").json() == {
            "status": "alive",
            "service": "incidentiq-api",
        }
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
    event = json.loads(caplog.records[-1].message)
    assert event["path"] == "/health/ready"
    assert event["status_code"] == 200


def test_not_ready_does_not_break_liveness() -> None:
    with TestClient(create_app(Settings(ready=False))) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INCIDENTIQ_READY", "false")
    monkeypatch.setenv("INCIDENTIQ_ENV", "test")
    assert load_settings() == Settings(environment="test", ready=False)


def test_readiness_requires_startup_and_resets_on_shutdown() -> None:
    app = create_app(Settings())
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
    assert app.state.started is False
    # No context manager deliberately skips lifespan startup.
    client = TestClient(app)
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200
    client.close()


def test_invalid_configuration_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INCIDENTIQ_READY", "invalid")
    with pytest.raises(ValidationError):
        load_settings()


@pytest.mark.parametrize("enabled", [True, False])
def test_health_responses_are_not_cacheable(enabled: bool) -> None:
    with TestClient(create_app(Settings(ready=enabled))) as client:
        for path in ("/health/live", "/health/ready"):
            assert client.get(path).headers["cache-control"] == "no-store"


def test_readiness_failure_is_documented() -> None:
    schema = create_app(Settings()).openapi()
    responses = schema["paths"]["/health/ready"]["get"]["responses"]
    assert "503" in responses
    assert responses["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ReadinessResponse",
    }


def test_api_env_loading_and_environment_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from incidentiq import config

    path = tmp_path / "api.env"
    path.write_text("INCIDENTIQ_ENV=test\nINCIDENTIQ_READY=false\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", path)
    monkeypatch.delenv("INCIDENTIQ_ENV", raising=False)
    monkeypatch.delenv("INCIDENTIQ_READY", raising=False)
    assert load_settings() == Settings(environment="test", ready=False)
    monkeypatch.setenv("INCIDENTIQ_READY", "true")
    assert load_settings().ready is True
