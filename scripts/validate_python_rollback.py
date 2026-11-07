"""Reject a changed dependency environment and restore isolated, verified Python A."""

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from incidentiq.infrastructure.usage_budget import UsageBudget

from scripts.local_release import ROOT, create_snapshot, verify_snapshot
from scripts.python_release import build_environment, minimal_environment, seal_wheelhouse
from scripts.validate_local_release import process, wait


def main():
    wheel_hash = seal_wheelhouse()
    print("Pinned wheelhouse hashes verified", flush=True)
    baseline, python, baseline_hash = build_environment(wheel_hash)
    print("Isolated baseline environment installed offline and verified", flush=True)
    candidate, _, candidate_hash = build_environment(wheel_hash)
    print("Separate candidate environment installed offline and verified", flush=True)
    artifact, source_hash = create_snapshot()
    private = ROOT / ".cache/access/python-rollback" / str(uuid4())
    private.mkdir(parents=True)
    actor = json.loads((ROOT / "docs/access-provisioning.json").read_text())
    user_id = str(uuid4())
    token = secrets.token_urlsafe(40)
    registry = private / "tokens.json"
    registry.write_text(
        json.dumps(
            [
                {
                    "user_id": user_id,
                    "tenant_id": actor["tenant_id"],
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": time.time() + 3600,
                    "scopes": ["incidents:read", "investigations:read", "investigations:write"],
                }
            ]
        )
    )
    env = minimal_environment()
    env.update({k: v for k, v in dotenv_values(ROOT / "apps/api/api.env").items() if v is not None})
    env.update(
        INCIDENTIQ_AUTH_ENABLED="true",
        INCIDENTIQ_ENV="production",
        INCIDENTIQ_READY="true",
        INCIDENTIQ_TOKEN_REGISTRY=str(registry),
        INCIDENTIQ_DATA_DIR=str(private / "data"),
        PYTHONPATH=str(artifact / "apps/api/src") + os.pathsep + str(artifact),
    )
    ledger = private / "data/access/usage.sqlite"
    UsageBudget(ledger).reserve(user_id, 12345)
    headers = {"Authorization": f"Bearer {token}"}
    run = None
    rejected = False
    for stage in ("baseline", "candidate", "rollback"):
        if stage == "candidate":
            dependency = candidate / "Lib/site-packages/starlette/__init__.py"
            if not dependency.is_file():
                dependency = next(candidate.glob("lib/python*/site-packages/starlette/__init__.py"))
            dependency.write_bytes(
                dependency.read_bytes() + b"\nraise RuntimeError('drill fault')\n"
            )
            try:
                verify_snapshot(candidate, candidate_hash)
            except ValueError as error:
                if str(error) != "snapshot_file_changed":
                    raise
                rejected = True
            assert rejected
            print("Tampered candidate rejected before execution", flush=True)
            continue
        verify_snapshot(artifact, source_hash)
        verify_snapshot(baseline, baseline_hash)
        probe = subprocess.run(
            [
                str(python),
                "-B",
                "-c",
                "import json,sys,incidentiq,fastapi; "
                "print(json.dumps([sys.prefix,incidentiq.__file__,fastapi.__file__]))",
            ],
            cwd=artifact,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        prefix, source, library = json.loads(probe.stdout)
        assert Path(prefix).resolve() == baseline.resolve()
        assert Path(source).resolve().is_relative_to(artifact)
        assert Path(library).resolve().is_relative_to(baseline)
        command = [
            str(python),
            "-B",
            "-m",
            "uvicorn",
            "incidentiq.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8004",
            "--no-access-log",
        ]
        with process(command, env, f"python-{stage}", cwd=artifact) as child:
            with httpx.Client(
                base_url="http://127.0.0.1:8004", timeout=10, trust_env=False
            ) as client:
                wait(client, "/health/ready", child=child)
                assert client.get("/api/v1/incidents").status_code == 401
                assert client.get("/api/v1/incidents", headers=headers).status_code == 200
                if run is None:
                    response = client.post(
                        "/api/v1/investigations",
                        headers=headers,
                        json={"question": "Isolated Python checkpoint drill", "provider": "mock"},
                    )
                    assert response.status_code == 200
                    run = response.json()
                    assert run["status"] == "awaiting_approval" and not run["published"]
                else:
                    current = client.get(f"/api/v1/investigations/{run['run_id']}", headers=headers)
                    assert current.status_code == 200
                    assert current.json()["report_sha256"] == run["report_sha256"]
                    assert current.json()["published"] is False
                assert (
                    client.post(
                        f"/api/v1/investigations/{run['run_id']}/approve",
                        headers=headers,
                        json={"report_sha256": run["report_sha256"]},
                    ).status_code
                    == 403
                )
        verify_snapshot(baseline, baseline_hash)
        verify_snapshot(artifact, source_hash)
        with closing(sqlite3.connect(ledger)) as connection:
            assert connection.execute(
                "SELECT spent FROM usage WHERE user_id=?", (user_id,)
            ).fetchone() == (12345,)
        print(f"{stage}: authenticated API, checkpoint and budget ledger verified", flush=True)
    receipt = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "isolated_python_environment_rollback": True,
        "offline_hash_required_install": True,
        "wheelhouse_sha256": wheel_hash,
        "baseline_environment_sha256": baseline_hash,
        "candidate_environment_sha256": candidate_hash,
        "source_sha256": source_hash,
        "tampered_dependency_rejected_before_execution": rejected,
        "sequence": ["baseline_ready", "candidate_rejected", "baseline_restored_ready"],
        "authenticated_reads": True,
        "unauthenticated_reads_denied": True,
        "checkpoint_preserved": True,
        "budget_ledger_preserved": True,
        "unauthorized_approval_denied": True,
        "development_site_packages_used": False,
        "host_python_runtime_shared": True,
        "dependency_version_upgrade_tested": False,
        "paid_model_calls": 0,
        "schema_changes": False,
    }
    (ROOT / "docs/python-rollback-validation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        trace = error.__traceback__
        while trace.tb_next:
            trace = trace.tb_next
        print(f"python_rollback_failed: {type(error).__name__} line {trace.tb_lineno}")
        raise SystemExit(1) from None
