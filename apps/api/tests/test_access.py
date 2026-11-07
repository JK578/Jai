import hashlib
import json
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from incidentiq.config import Settings
from incidentiq.domain.access import AccessDenied
from incidentiq.infrastructure.access import TokenRegistry
from incidentiq.main import create_app


def registry(tmp_path):
    path = tmp_path / "tokens.json"
    scopes = [
        "incidents:read",
        "incidents:write",
        "logs:read",
        "investigations:read",
        "investigations:write",
        "investigations:approve",
    ]
    entries = [
        {
            "user_id": str(UUID(int=n)),
            "tenant_id": str(UUID(int=n)),
            "token_sha256": hashlib.sha256((str(n) * 48).encode()).hexdigest(),
            "expires_at": time.time() + 3600,
            "scopes": scopes if n != 3 else ["incidents:read"],
        }
        for n in (1, 2, 3)
    ]
    path.write_text(json.dumps(entries))
    return path


def test_authentication_and_tenant_isolation(tmp_path):
    path = registry(tmp_path)
    app = create_app(Settings(storage="memory", auth_enabled=True, token_registry=path))
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/v1/incidents").status_code == 401
        assert (
            client.get("/api/v1/incidents", headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        first = {"Authorization": "Bearer " + "1" * 48}
        second = {"Authorization": "Bearer " + "2" * 48}
        result = client.post(
            "/api/v1/incidents",
            headers=first,
            json={"title": "private", "description": "tenant one", "service_name": "service"},
        )
        assert result.status_code == 201
        identity = result.json()["id"]
        assert len(client.get("/api/v1/incidents", headers=first).json()) == 1
        assert client.get("/api/v1/incidents", headers=second).json() == []
        assert client.get(f"/api/v1/incidents/{identity}", headers=second).status_code == 404
        assert client.get("/api/v1/auth/session", headers=first).json()["tenant_id"] == str(
            UUID(int=1)
        )
        denied = client.post(
            "/api/v1/incidents",
            headers={"Authorization": "Bearer " + "3" * 48},
            json={"title": "blocked"},
        )
        assert denied.status_code == 403


def test_expiry_revocation_and_malformed_registry_fail_closed(tmp_path):
    path = registry(tmp_path)
    verifier = TokenRegistry(path)
    assert verifier.authenticate("1" * 48).tenant_id == UUID(int=1)
    entries = json.loads(path.read_text())
    entries[0]["revoked"] = True
    entries[1]["expires_at"] = 0
    path.write_text(json.dumps(entries))
    for token in ("1" * 48, "2" * 48, "x" * 1000):
        with pytest.raises(AccessDenied):
            verifier.authenticate(token)
    path.write_text("not JSON")
    with pytest.raises(AccessDenied):
        verifier.authenticate("1" * 48)


def test_production_cannot_disable_auth():
    with pytest.raises(ValueError, match="Production requires authentication"):
        Settings(environment="production", auth_enabled=False)
