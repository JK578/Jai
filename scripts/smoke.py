"""Exercise built Next.js and FastAPI over real loopback HTTP. No browser needed."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 18000
WEB_PORT = 13000


def get(url: str) -> tuple[int, str]:
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
    node = os.environ.get("NODE_EXE", r"C:\Program Files\nodejs\node.exe")
    api_url = f"http://127.0.0.1:{API_PORT}"
    web_url = f"http://127.0.0.1:{WEB_PORT}"
    processes: list[subprocess.Popen[bytes]] = []
    with tempfile.TemporaryFile() as logs:
        try:
            web_env = {**os.environ, "BACKEND_URL": api_url, "NEXT_TELEMETRY_DISABLED": "1"}
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
                    env={**os.environ, "INCIDENTIQ_READY": flag},
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
                stop(api)
                processes.remove(api)
            page_code, html = get(web_url)
            assert page_code == 200 and "Backend unavailable" in html
            print("PASS: stopped API; frontend 'Backend unavailable'")
        except BaseException:
            logs.seek(0)
            print(logs.read().decode(errors="replace"), file=sys.stderr)
            raise
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
