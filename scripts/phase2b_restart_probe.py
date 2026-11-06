"""Verify persistence through two real API processes, using read-only loopback HTTP."""

import json
import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from incidentiq.infrastructure.log_source import manifest

from scripts.validate_phase2b_live import ROOT, save


def probe() -> None:
    observations = []
    for _ in range(2):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "incidentiq.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env={**os.environ, "INCIDENTIQ_ENV": "development", "INCIDENTIQ_STORAGE": "postgres"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"

            def get(path: str, origin: str = base):
                with urlopen(origin + path, timeout=10) as response:
                    return json.load(response)

            deadline = time.monotonic() + 30
            while True:
                try:
                    assert get("/health/ready")["status"] == "ready"
                    break
                except Exception:
                    if time.monotonic() > deadline or process.poll() is not None:
                        raise RuntimeError("API startup failed") from None
                    time.sleep(0.25)
            ids = []
            cursor = 0
            while True:
                page = get(f"/api/v1/logs?file_id={manifest().file_id}&limit=100&cursor={cursor}")
                ids.extend(item["id"] for item in page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            assert len(ids) == len(set(ids)) == 2000
            assert get("/health/live")["status"] == "alive"
            assert len(get("/api/v1/incidents")) == 1
            observations.append(ids)
        finally:
            process.terminate()
            process.wait(timeout=15)
    assert observations[0] == observations[1]
    save(
        "process_restart",
        {
            "distinct_api_processes": 2,
            "persisted_events": 2000,
            "all_event_ids_identical_after_restart": True,
            "incident_count": 1,
            "readiness_pass": True,
        },
    )


if __name__ == "__main__":
    try:
        probe()
    except Exception:
        print("STOP: process restart probe failed; sensitive details suppressed")
        raise SystemExit(1) from None
