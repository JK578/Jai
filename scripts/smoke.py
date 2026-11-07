"""Exercise built Next.js and FastAPI over real loopback HTTP. No browser needed."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 18000
WEB_PORT = 13000


def get(url: str | Request) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=6) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def wait_for(url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            get(url)
            return
        except URLError, TimeoutError:
            time.sleep(0.25)
    raise RuntimeError(f"Server did not start: {url}")


def stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Opt-in live persistence test; retains one new evidence incident",
    )
    args = parser.parse_args()
    node = os.environ.get("NODE_EXE", r"C:\Program Files\nodejs\node.exe")
    api_url = f"http://127.0.0.1:{API_PORT}"
    web_url = f"http://127.0.0.1:{WEB_PORT}"
    processes: list[subprocess.Popen[bytes]] = []
    with tempfile.TemporaryFile() as logs:
        try:
            web_env = {
                **os.environ,
                "BACKEND_URL": api_url,
                "NEXT_TELEMETRY_DISABLED": "1",
                "INCIDENTIQ_AUTH_ENABLED": "false",
            }
            web = subprocess.Popen(
                [
                    node,
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(WEB_PORT),
                ],
                cwd=ROOT / "apps/web",
                env=web_env,
                stdout=logs,
                stderr=logs,
            )
            processes.append(web)
            wait_for(web_url)
            for flag, code, label in [
                ("true", 200, "Connected · backend ready"),
                ("false", 503, "Connected · backend not ready"),
            ]:
                api = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "incidentiq.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(API_PORT),
                    ],
                    cwd=ROOT,
                    env={
                        **os.environ,
                        "INCIDENTIQ_READY": flag,
                        "INCIDENTIQ_AUTH_ENABLED": "false",
                        "INCIDENTIQ_STORAGE": "postgres" if args.postgres else "memory",
                    },
                    stdout=logs,
                    stderr=logs,
                )
                processes.append(api)
                wait_for(f"{api_url}/health/live")
                assert get(f"{api_url}/health/live")[0] == 200
                assert get(f"{api_url}/health/ready")[0] == code
                page_code, html = get(web_url)
                assert page_code == 200 and label in html, label
                print(f"PASS: readiness {code}; frontend '{label}'")
                if flag == "true":
                    if not args.postgres:
                        assert json.loads(get(f"{web_url}/api/v1/incidents")[1]) == []
                    payload = {
                        "title": "Persistence verification" if args.postgres else "Smoke incident",
                        "description": "Development verification record; retained as evidence"
                        if args.postgres
                        else "Local HTTP workflow",
                        "severity": "high",
                        "service_name": "checkout-api",
                    }
                    create_code, created_body = get(
                        Request(
                            f"{web_url}/api/v1/incidents",
                            data=json.dumps(payload).encode(),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                    )
                    assert create_code == 201
                    created = json.loads(created_body)
                    assert created["status"] == "open"
                    assert created in json.loads(get(f"{web_url}/api/v1/incidents")[1])
                    detail_code, detail_body = get(f"{web_url}/api/v1/incidents/{created['id']}")
                    assert detail_code == 200 and json.loads(detail_body) == created
                    invalid_code, _ = get(
                        Request(
                            f"{web_url}/api/v1/incidents",
                            data=b"{}",
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                    )
                    assert invalid_code == 422
                    assert (
                        get(f"{web_url}/api/v1/incidents/00000000-0000-0000-0000-000000000000")[0]
                        == 404
                    )
                    print("PASS: incident create/list/detail and validation through Next.js proxy")
                else:
                    if args.postgres:
                        assert (
                            json.loads(get(f"{web_url}/api/v1/incidents/{created['id']}")[1])
                            == created
                        )
                        assert created in json.loads(get(f"{web_url}/api/v1/incidents")[1])
                        print("PASS: incident persists after real backend process restart")
                    else:
                        assert json.loads(get(f"{web_url}/api/v1/incidents")[1]) == []
                        print("PASS: backend restart clears in-memory incidents")
                stop(api)
                processes.remove(api)
            page_code, html = get(web_url)
            assert page_code == 200 and "Backend unavailable" in html
            print("PASS: stopped API; frontend 'Backend unavailable'")
            assert get(f"{web_url}/api/v1/incidents")[0] == 502
            print("PASS: stopped API; incident proxy returns 502")
        except BaseException:
            logs.seek(0)
            print(logs.read().decode(errors="replace"), file=sys.stderr)
            raise
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
