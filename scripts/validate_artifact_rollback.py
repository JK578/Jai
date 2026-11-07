"""Run secure backend A, fault-injected backend B, then restore verified artifact A."""

import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

from scripts.local_release import ROOT, create_snapshot, verify_snapshot
from scripts.validate_local_release import process, wait


def main():
    baseline, baseline_hash = create_snapshot()
    candidate, candidate_hash = create_snapshot(fault=True)
    private = ROOT / ".cache/access/artifact-rollback" / str(uuid4())
    private.mkdir(parents=True)
    actor = json.loads((ROOT / "docs/access-provisioning.json").read_text())
    token = secrets.token_urlsafe(40)
    registry = private / "tokens.json"
    registry.write_text(
        json.dumps(
            [
                {
                    "user_id": str(uuid4()),
                    "tenant_id": actor["tenant_id"],
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": time.time() + 3600,
                    "scopes": [
                        "incidents:read",
                        "logs:read",
                        "investigations:read",
                        "investigations:write",
                    ],
                }
            ]
        )
    )
    values = dotenv_values(ROOT / "apps/api/api.env")
    env = os.environ.copy()
    env.update({key: value for key, value in values.items() if value is not None})
    env.update(
        INCIDENTIQ_AUTH_ENABLED="true",
        INCIDENTIQ_ENV="production",
        INCIDENTIQ_READY="true",
        INCIDENTIQ_TOKEN_REGISTRY=str(registry),
        INCIDENTIQ_DATA_DIR=str(private / "data"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "incidentiq.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8002",
        "--no-access-log",
    ]
    headers = {"Authorization": f"Bearer {token}"}
    paths = []
    run = None
    for name, artifact, fingerprint, code in [
        ("baseline", baseline, baseline_hash, 200),
        ("candidate", candidate, candidate_hash, 503),
        ("rollback", baseline, baseline_hash, 200),
    ]:
        verify_snapshot(artifact, fingerprint)
        child_env = env | {
            "PYTHONPATH": os.pathsep.join([str(artifact / "apps/api/src"), str(artifact)])
        }
        # Confirm import resolution before serving: never silently run the editable checkout.
        probe = subprocess.run(
            [sys.executable, "-c", "import incidentiq; print(incidentiq.__file__)"],
            cwd=artifact,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        resolved = Path(probe.stdout.strip()).resolve()
        assert resolved.is_relative_to(artifact.resolve())
        paths.append(resolved.relative_to(artifact).as_posix())
        with process(command, child_env, f"artifact-{name}", cwd=artifact) as child:
            with httpx.Client(
                base_url="http://127.0.0.1:8002", timeout=10, trust_env=False
            ) as client:
                wait(client, "/health/ready", code)
                assert child.poll() is None
                assert client.get("/api/v1/incidents").status_code == 401
                assert client.get("/api/v1/incidents", headers=headers).status_code == 200
                if name == "baseline":
                    response = client.post(
                        "/api/v1/investigations",
                        headers=headers,
                        json={"question": "Artifact persistence drill", "provider": "mock"},
                    )
                    assert response.status_code == 200
                    run = response.json()
                    assert run["status"] == "awaiting_approval" and not run["published"]
                else:
                    current = client.get(f"/api/v1/investigations/{run['run_id']}", headers=headers)
                    assert current.status_code == 200
                    assert current.json()["report_sha256"] == run["report_sha256"]
                    assert current.json()["published"] is False
        verify_snapshot(artifact, fingerprint)
    receipt = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "backend_source_artifact_rollback": True,
        "baseline_manifest_sha256": baseline_hash,
        "candidate_manifest_sha256": candidate_hash,
        "fault_injected_candidate": True,
        "readiness_sequence": [200, 503, 200],
        "authenticated_reads_on_all_artifacts": True,
        "unauthenticated_requests_denied": True,
        "private_checkpoint_preserved": True,
        "imports_resolved_inside_artifacts": paths,
        "shared_python_environment": True,
        "frontend_artifact_rollback": False,
        "schema_changed": False,
        "paid_model_calls": 0,
    }
    (ROOT / "docs/artifact-rollback-validation.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        trace = error.__traceback__
        while trace.tb_next:
            trace = trace.tb_next
        print(f"artifact_rollback_failed: {type(error).__name__} line {trace.tb_lineno}")
        raise SystemExit(1) from None
