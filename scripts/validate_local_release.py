"""Exercise local authenticated release and configuration rollback without paid calls."""

import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".cache/access/release-check"


@contextmanager
def process(command, env, name, cwd=ROOT):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with (PRIVATE / f"{name}.log").open("w", encoding="utf-8") as output:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=output)
        try:
            yield child
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def wait(client, path, expected=200, *, child=None):
    for _ in range(60):
        if child is not None and child.poll() is not None:
            raise RuntimeError("local_service_exited")
        try:
            response = client.get(path)
            if response.status_code == expected:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("local_service_not_ready")


def mcp(token, origin):
    # Deliberately omit owner database URL, OpenAI credentials and tracing credentials.
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    env.update(INCIDENTIQ_MCP_TOKEN=token, INCIDENTIQ_MCP_API=origin)
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_log_files", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "execute_sql", "arguments": {}},
        },
    ]
    result = subprocess.run(
        [sys.executable, "-m", "incidentiq.mcp_server"],
        env=env,
        cwd=ROOT,
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        timeout=40,
        check=True,
    )
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 4 and not result.stderr
    assert rows[0]["result"]["serverInfo"]["name"] == "incidentiq-evidence"
    assert len(rows[1]["result"]["tools"]) == 5
    assert rows[2]["result"]["isError"] is False
    assert rows[3]["error"]["code"] == -32602


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    values = dotenv_values(ROOT / "apps/api/api.env")
    provisioned = json.loads((ROOT / "docs/access-provisioning.json").read_text())
    first, second = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    scopes = [
        "incidents:read",
        "incidents:write",
        "logs:read",
        "search:run",
        "investigations:read",
        "investigations:write",
        "investigations:approve",
    ]
    entries = [
        {
            "user_id": str(uuid4()),
            "tenant_id": tenant,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": time.time() + 3600,
            "scopes": scopes,
        }
        for token, tenant in [(first, provisioned["tenant_id"]), (second, str(uuid4()))]
    ]
    registry = PRIVATE / "tokens.json"
    registry.write_text(json.dumps(entries))
    env = os.environ.copy()
    env.update({key: value for key, value in values.items() if value is not None})
    env.update(
        INCIDENTIQ_AUTH_ENABLED="true",
        INCIDENTIQ_ENV="production",
        INCIDENTIQ_TOKEN_REGISTRY=str(registry),
        INCIDENTIQ_READY="true",
    )
    api = "http://127.0.0.1:8001"
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "incidentiq.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
        "--no-access-log",
    ]
    with httpx.Client(base_url=api, timeout=10, trust_env=False) as client:
        with process(command, env, "api"):
            wait(client, "/health/ready")
            assert client.get("/api/v1/incidents").status_code == 401
            headers = {"Authorization": f"Bearer {first}"}
            other = {"Authorization": f"Bearer {second}"}
            catalog = client.get("/api/v1/log-datasets", headers=headers)
            assert catalog.status_code == 200 and len(catalog.json()["items"]) == 1
            assert client.get("/api/v1/log-datasets", headers=other).json()["items"] == []
            assert client.get("/api/v1/incidents", headers=other).json() == []
            file_id = catalog.json()["items"][0]["file_id"]
            logs = client.get(
                "/api/v1/logs", headers=headers, params={"file_id": file_id, "limit": 20}
            )
            assert logs.status_code == 200 and len(logs.json()["items"]) == 20
            event_id = logs.json()["items"][0]["id"]
            assert client.get(f"/api/v1/logs/{event_id}", headers=other).status_code == 404
            assert (
                client.post(
                    "/api/v1/search", headers=other, json={"question": "denied before model"}
                ).status_code
                == 404
            )
            started = client.post(
                "/api/v1/investigations",
                headers=headers,
                json={"question": "Validate local demo approval", "provider": "mock"},
            )
            assert started.status_code == 200
            draft = started.json()
            assert draft["status"] == "awaiting_approval" and not draft["published"]
            path = f"/api/v1/investigations/{draft['run_id']}"
            assert client.get(path, headers=other).status_code == 404
            assert (
                client.post(
                    path + "/approve", headers=headers, json={"report_sha256": "0" * 64}
                ).status_code
                == 409
            )
            approved = client.post(
                path + "/approve", headers=headers, json={"report_sha256": draft["report_sha256"]}
            )
            assert approved.status_code == 200 and approved.json()["published"]
            mcp(first, api)
            web_env = os.environ.copy()
            for key in list(web_env):
                if key.startswith(("DATABASE_", "OPENAI_", "LANGCHAIN_", "LANGSMITH_")):
                    del web_env[key]
            web_env.update(BACKEND_URL=api, INCIDENTIQ_AUTH_ENABLED="true")
            web_command = [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                "3001",
            ]
            with process(web_command, web_env, "web", ROOT / "apps/web"):
                with httpx.Client(
                    base_url="http://127.0.0.1:3001", timeout=15, trust_env=False
                ) as web:
                    page = wait(web, "/")
                    assert "Sign in" in page.text
                    assert web.get("/api/v1/incidents").status_code == 401
                    assert (
                        web.post(
                            "/api/auth/login",
                            json={"token": first},
                            headers={"Origin": "http://evil.example"},
                        ).status_code
                        == 403
                    )
                    login = web.post(
                        "/api/auth/login",
                        json={"token": first},
                        headers={"Origin": "http://127.0.0.1:3001"},
                    )
                    assert login.status_code == 200 and first not in login.text
                    assert "HttpOnly" in login.headers["set-cookie"]
                    assert web.get("/api/v1/incidents").status_code == 200
                    assert web.get("/api/workspace/log-datasets").status_code == 200
                    assert "Investigations" in web.get("/").text
                    assert (
                        web.post(
                            "/api/auth/logout", headers={"Origin": "http://127.0.0.1:3001"}
                        ).status_code
                        == 200
                    )
                    assert web.get("/api/v1/incidents").status_code == 401
            entries[0]["revoked"] = True
            registry.write_text(json.dumps(entries))
            assert client.get("/api/v1/incidents", headers=headers).status_code == 401
        # Deliberately failed candidate configuration, then restore the secure configuration.
        with process(command, env | {"INCIDENTIQ_READY": "false"}, "not-ready"):
            wait(client, "/health/ready", 503)
            assert client.get("/health/live").status_code == 200
        with process(command, env, "restored"):
            wait(client, "/health/ready")
            assert client.get("/api/v1/incidents").status_code == 401
    receipt = {
        "authenticated_api": True,
        "runtime_tenant_isolation": True,
        "digest_bound_approval": True,
        "mcp_stdio": True,
        "production_frontend_login_proxy_logout": True,
        "token_revocation": True,
        "configuration_rollback": True,
        "paid_model_calls": 0,
        "cloud_deployment": False,
        "browser_visual_qa": False,
    }
    (ROOT / "docs/local-release-validation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never expose HTTP headers, environment, SQL parameters or credential values.
        trace = error.__traceback__
        while trace.tb_next:
            trace = trace.tb_next
        print(f"local_release_failed: {type(error).__name__} line {trace.tb_lineno}")
        raise SystemExit(1) from None
