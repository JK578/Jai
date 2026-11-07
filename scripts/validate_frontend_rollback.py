"""Verify standalone frontend A, fault candidate B and restored A with bundled dependencies."""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

from scripts.frontend_release import create_frontend_snapshot
from scripts.local_release import ROOT, verify_snapshot
from scripts.validate_local_release import process, wait


def main():
    baseline, first_hash = create_frontend_snapshot()
    print("frontend baseline package verified", flush=True)
    candidate, second_hash = create_frontend_snapshot(fault=True)
    print("frontend fault candidate package verified", flush=True)
    private = ROOT / ".cache/access/frontend-rollback" / str(uuid4())
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
                    "scopes": ["incidents:read", "logs:read"],
                }
            ]
        )
    )
    api_env = os.environ.copy()
    api_env.update(
        {k: v for k, v in dotenv_values(ROOT / "apps/api/api.env").items() if v is not None}
    )
    api_env.update(
        INCIDENTIQ_AUTH_ENABLED="true",
        INCIDENTIQ_ENV="production",
        INCIDENTIQ_READY="true",
        INCIDENTIQ_TOKEN_REGISTRY=str(registry),
        INCIDENTIQ_DATA_DIR=str(private / "data"),
    )
    api = "http://127.0.0.1:8003"
    origin = "http://127.0.0.1:3002"
    api_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "incidentiq.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8003",
        "--no-access-log",
    ]
    node = shutil.which("node")
    if not node:
        raise ValueError("node_required")
    web_env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    web_env.update(
        PORT="3002",
        HOSTNAME="127.0.0.1",
        BACKEND_URL=api,
        INCIDENTIQ_AUTH_ENABLED="true",
        NODE_ENV="production",
        NEXT_TELEMETRY_DISABLED="1",
    )
    asset_count = 0
    with process(api_command, api_env, "frontend-rollback-api"):
        with httpx.Client(base_url=api, trust_env=False, timeout=10) as client:
            wait(client, "/health/ready")
        with httpx.Client(base_url=origin, trust_env=False, timeout=15) as web:
            for name, artifact, fingerprint, expected in [
                ("baseline", baseline, first_hash, 200),
                ("candidate", candidate, second_hash, 503),
                ("rollback", baseline, first_hash, 200),
            ]:
                manifest = verify_snapshot(artifact, fingerprint)
                entry = artifact / manifest["entrypoint"]
                resolved = subprocess.run(
                    [node, "-p", "require.resolve('next')"],
                    cwd=entry.parent,
                    env=web_env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                assert Path(resolved.stdout.strip()).resolve().is_relative_to(artifact)
                with process(
                    [node, str(entry)], web_env, f"frontend-{name}", cwd=entry.parent
                ) as child:
                    page = wait(web, "/", expected, child=child)
                    assert child.poll() is None
                    if name == "candidate":
                        assert web.get("/api/v1/incidents").status_code == 503
                        continue
                    if name == "baseline":
                        assert "Sign in" in page.text
                        assert web.get("/api/v1/incidents").status_code == 401
                        login = web.post(
                            "/api/auth/login", json={"token": token}, headers={"Origin": origin}
                        )
                        assert login.status_code == 200 and token not in login.text
                        assert "HttpOnly" in login.headers["set-cookie"]
                        page = web.get("/")
                    assert "Incident workspace" in page.text
                    assert token not in page.text
                    assert web.get("/api/v1/incidents").status_code == 200
                    catalog = web.get("/api/workspace/log-datasets")
                    assert catalog.status_code == 200 and len(catalog.json()["items"]) == 1
                    assets = set(
                        re.findall(r'(?:src|href)="([^" ]*/_next/static/[^" ]+)"', page.text)
                    )
                    assert assets
                    for asset in assets:
                        assert asset.startswith("/_next/static/")
                        response = web.get(asset.replace("&amp;", "&"))
                        assert response.status_code == 200
                    asset_count = len(assets)
                    if name == "rollback":
                        assert (
                            web.post("/api/auth/logout", headers={"Origin": origin}).status_code
                            == 200
                        )
                        assert web.get("/api/v1/incidents").status_code == 401
                verify_snapshot(artifact, fingerprint)
    receipt = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "frontend_artifact_rollback": True,
        "bundled_next_dependencies": True,
        "workspace_node_modules_required": False,
        "baseline_manifest_sha256": first_hash,
        "candidate_manifest_sha256": second_hash,
        "fault_injected_candidate": True,
        "status_sequence": [200, 503, 200],
        "session_survived_rollback": True,
        "authenticated_proxy_and_tenant_catalog": True,
        "static_assets_checked": asset_count,
        "environment_files_excluded": True,
        "paid_model_calls": 0,
        "node_runtime_shared": True,
        "browser_visual_qa": False,
    }
    (ROOT / "docs/frontend-rollback-validation.json").write_text(
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
        print(f"frontend_rollback_failed: {type(error).__name__} line {trace.tb_lineno}")
        raise SystemExit(1) from None
