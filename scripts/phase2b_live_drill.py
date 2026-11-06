"""Authorized development-only ingestion drill; no DDL, deletes, or lease manipulation."""

import argparse
import ctypes
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from incidentiq.application.log_ingestion import ingest
from incidentiq.config import load_settings
from incidentiq.domain.logs import LogBusy
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.log_source import manifest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from scripts.validate_phase2b_live import ROOT, log_storage, save


class DrillStop(RuntimeError):
    pass


class FencingVerified(Exception):
    pass


def memory() -> dict[str, int]:
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in ("peak", "working", "qpp", "qp", "qnp", "qn", "page", "peakpage")
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = wintypes.HANDLE
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(current(), ctypes.byref(counters), counters.cb):
        raise DrillStop("memory_measurement_failed")
    return {"working_set_bytes": counters.working, "peak_working_set_bytes": counters.peak}


def engine_for_development():
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise DrillStop("development_database_required")
    engine = database_engine(settings.database_url, pooled=False)
    url = engine.url
    reference = "ngwondsdwnbmvawyszey"
    if not (
        url.host == f"db.{reference}.supabase.co"
        or (
            (url.host or "").endswith(".pooler.supabase.com")
            and url.username == f"postgres.{reference}"
        )
    ):
        engine.dispose()
        raise DrillStop("unapproved_project")
    with engine.connect() as connection:
        if (
            connection.scalar(text("SELECT version_num FROM public.incidentiq_alembic_version"))
            != "0002_logs"
        ):
            raise DrillStop("unexpected_revision")
    return engine


def write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, default=str), encoding="utf-8")
    temporary.replace(path)


def wait_file(path: Path, timeout: int = 180) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.2)
    raise DrillStop("worker_signal_timeout")


def worker(args) -> None:
    engine = engine_for_development()
    source = manifest()
    path = ROOT / ".cache/loghub" / f"{source.sha256}.log"
    baseline = memory()
    first = True

    class ObservedRepository(PostgresLogRepository):
        def claim(self, source, token, resume):
            run = super().claim(source, token, resume)
            if args.mode == "successor":
                write(args.control / "claimed.json", {"run_id": str(run.id)})
                wait_file(args.control / "go.json")
            return run

        def commit_batch(self, run_id, token, batch):
            nonlocal first
            super().commit_batch(run_id, token, batch)
            if first and args.mode in {"crash", "old"}:
                first = False
                checkpoint = super().checkpoint(run_id, token)
                write(
                    args.control / "checkpoint.json",
                    {
                        "run_id": str(run_id),
                        "line": checkpoint.last_committed_line,
                        "lease_expires_at": checkpoint.lease_expires_at.isoformat(),
                        "memory_baseline": baseline,
                        "memory_at_checkpoint": memory(),
                    },
                )
                wait_file(args.control / "challenge.json")
                # The successor is now paused after claiming with a new token.
                blocked = 0
                for action in (
                    lambda: super(ObservedRepository, self).commit_batch(run_id, token, batch),
                    lambda: super(ObservedRepository, self).fail(run_id, token),
                ):
                    try:
                        action()
                    except LogBusy:
                        blocked += 1
                if blocked != 2:
                    raise DrillStop("stale_worker_modified_state")
                write(
                    args.control / "fenced.json",
                    {"stale_commit_blocked": True, "stale_fail_blocked": True},
                )
                raise FencingVerified

    repository = ObservedRepository(sessionmaker(engine, expire_on_commit=False))
    try:
        if args.mode == "contender":
            try:
                repository.claim(source, uuid4(), None)
            except LogBusy:
                write(args.control / "contender.json", {"concurrent_claim_blocked": True})
                return
            raise DrillStop("second_worker_claimed")
        result = asdict(ingest(repository, path, source, resume=args.resume))
        result.pop("owner_token")
        final_memory = memory()
        result["memory"] = {
            "baseline": baseline,
            "after": final_memory,
            "peak_minus_baseline_working_set_bytes": max(
                0, final_memory["peak_working_set_bytes"] - baseline["working_set_bytes"]
            ),
        }
        write(args.control / "result.json", result)
    except FencingVerified:
        return
    finally:
        engine.dispose()


def api_checks(expected_events: int) -> dict:
    from fastapi.testclient import TestClient
    from incidentiq.main import create_app

    source = manifest()
    all_ids = []
    sample = None
    for attempt in range(2):
        with TestClient(create_app()) as client:
            logging.getLogger("incidentiq").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
            incidents = client.get("/api/v1/incidents").json()
            assert len(incidents) == 1
            assert client.get(f"/api/v1/incidents/{incidents[0]['id']}").status_code == 200
            cursor = 0
            identities = []
            while True:
                response = client.get(
                    "/api/v1/logs",
                    params={"file_id": str(source.file_id), "limit": 100, "cursor": cursor},
                )
                assert response.status_code == 200
                page = response.json()
                for event in page["items"]:
                    assert "raw_line" not in event and event["event_time_utc"] is None
                    identities.append(event["id"])
                    sample = sample or event
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            assert len(identities) == len(set(identities)) == expected_events
            if attempt == 0:
                all_ids = identities
            else:
                assert identities == all_ids
            assert client.get(f"/api/v1/logs/{sample['id']}").json()["raw_line"]
            assert client.get("/api/v1/log-datasets").status_code == 200
            runs = client.get("/api/v1/log-ingestions").json()["items"]
            assert all("owner_token" not in run for run in runs)
            assert client.get(f"/api/v1/log-ingestions/{runs[0]['id']}/errors").status_code == 200
            filters = {
                "file_id": str(source.file_id),
                "level": sample["normalized_level"],
                "q": sample["message"][:10],
                "from_local": sample["event_time_local"],
                "to_local": sample["event_time_local"],
            }
            filtered = client.get("/api/v1/logs", params=filters)
            assert filtered.status_code == 200 and filtered.json()["items"]
            for item in filtered.json()["items"]:
                assert item["normalized_level"] == sample["normalized_level"]
                assert item["event_time_local"] == sample["event_time_local"]
            assert (
                client.get(
                    "/api/v1/logs",
                    params={"file_id": str(source.file_id), "from_local": "2006-01-01T00:00:00Z"},
                ).status_code
                == 422
            )
    return {
        "pagination_unique_complete": True,
        "filters": True,
        "detail": True,
        "incident_endpoints": True,
        "health_readiness": True,
        "new_application_instances_preserve_ids": True,
    }


def controller() -> None:
    directory = ROOT / ".cache/loghub" / f"live-drill-{uuid4()}"
    directory.mkdir(parents=True)
    children = []
    engine = engine_for_development()
    with engine.connect() as connection:
        initial_storage = log_storage(connection)
        if connection.scalar(text("SELECT count(*) FROM incidentiq.log_ingestion_runs")) != 0:
            raise DrillStop("unexpected_existing_runs")

    def start(mode: str, control: Path, resume=None):
        control.mkdir(exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "scripts.phase2b_live_drill",
            "--worker",
            "--mode",
            mode,
            "--control",
            str(control),
        ]
        if resume:
            command += ["--resume", str(resume)]
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        children.append(process)
        return process

    def completed(process, control):
        if process.wait(timeout=180) != 0:
            raise DrillStop("worker_failed")
        return wait_file(control / "result.json", 1)

    def wait_expiry(checkpoint):
        expiry = datetime.fromisoformat(checkpoint["lease_expires_at"])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                now = connection.scalar(text("SELECT clock_timestamp()"))
            if now >= expiry:
                return
            time.sleep(2)
        raise DrillStop("lease_did_not_expire")

    try:
        crash_dir = directory / "crash"
        process = start("crash", crash_dir)
        checkpoint = wait_file(crash_dir / "checkpoint.json")
        assert checkpoint["line"] == 250
        contender_dir = directory / "contender"
        contender = start("contender", contender_dir)
        assert contender.wait(timeout=30) == 0
        assert wait_file(contender_dir / "contender.json")["concurrent_claim_blocked"]
        process.terminate()
        process.wait(timeout=10)
        save("crash_checkpoint", checkpoint)
        print(
            "PASS: killed worker at checkpoint 250; concurrent claim blocked; waiting for lease",
            flush=True,
        )
        wait_expiry(checkpoint)
        resume_dir = directory / "resumed"
        first = completed(start("normal", resume_dir, checkpoint["run_id"]), resume_dir)
        assert first["processed"] == 2000 and first["last_committed_line"] == 2000
        save("first_ingestion_recovered", first)
        replay_dir = directory / "replay"
        replay = completed(start("normal", replay_dir), replay_dir)
        assert replay["inserted"] == 0 and replay["duplicates"] == first["inserted"]
        save("replay", replay)
        print("PASS: recovery reconciled 2000 lines; replay inserted zero events", flush=True)
        old_dir = directory / "old"
        old = start("old", old_dir)
        old_checkpoint = wait_file(old_dir / "checkpoint.json")
        print(
            "Stale-worker drill: waiting for natural lease expiry; no database clock/lease edits",
            flush=True,
        )
        wait_expiry(old_checkpoint)
        successor_dir = directory / "successor"
        successor = start("successor", successor_dir, old_checkpoint["run_id"])
        wait_file(successor_dir / "claimed.json")
        write(old_dir / "challenge.json", {})
        fencing = wait_file(old_dir / "fenced.json")
        assert old.wait(timeout=10) == 0
        write(successor_dir / "go.json", {})
        successor_result = completed(successor, successor_dir)
        assert successor_result["processed"] == 2000 and successor_result["inserted"] == 0
        save(
            "fencing",
            {
                **fencing,
                "concurrent_claim_blocked": True,
                "successor_completed": True,
                "natural_lease_expiry": True,
            },
        )
        checks = api_checks(first["inserted"])
        save("api_checks", checks)
        with engine.connect() as connection:
            final_storage = log_storage(connection)
            states = dict(
                connection.execute(
                    text("SELECT state,count(*) FROM incidentiq.log_ingestion_runs GROUP BY state")
                ).all()
            )
            count = connection.scalar(text("SELECT count(*) FROM incidentiq.log_events"))
        memory_delta = max(
            first["memory"]["peak_minus_baseline_working_set_bytes"],
            replay["memory"]["peak_minus_baseline_working_set_bytes"],
        )
        result = {
            "source_lines": 2000,
            "persisted_events": count,
            "rejected_lines": first["rejected"],
            "replay_duplicates": replay["duplicates"],
            "run_states": states,
            "storage_before_public_bytes": initial_storage,
            "storage_final_bytes": final_storage,
            "storage_increment_public_bytes": final_storage - initial_storage,
            "storage_total_increment_since_0001_bytes": final_storage,
            "measured_worker_peak_minus_baseline_bytes": memory_delta,
            "storage_target_pass": final_storage < 10 * 1024**2,
            "memory_target_pass": memory_delta < 100 * 1024**2,
        }
        save("measurements", result)
        if not result["storage_target_pass"] or not result["memory_target_pass"]:
            raise DrillStop("resource_target_exceeded")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument(
        "--mode", choices=["normal", "crash", "old", "successor", "contender"], default="normal"
    )
    parser.add_argument("--control", type=Path)
    parser.add_argument("--resume", type=UUID)
    args = parser.parse_args()
    try:
        worker(args) if args.worker else controller()
    except Exception:
        print("STOP: controlled drill failed; sensitive details suppressed", flush=True)
        raise SystemExit(1) from None
