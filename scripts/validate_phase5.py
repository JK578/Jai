"""Fresh-process workflow checks; live mode stops at the human approval boundary."""

import argparse
import json
import sqlite3
import subprocess
import sys

from incidentiq.infrastructure.log_source import manifest

from scripts.investigate import RUNS
from scripts.retrieval_cli import ROOT, open_index, save


def invoke(*args, successful=True):
    process = subprocess.run(
        [sys.executable, "-m", "scripts.investigate", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if successful:
        if process.returncode:
            raise RuntimeError("workflow subprocess failed")
        return json.loads(process.stdout)
    assert process.returncode != 0
    return None


def calls(run_id):
    connection = sqlite3.connect(RUNS / run_id / "calls.sqlite")
    try:
        return connection.execute("SELECT stage, state FROM calls ORDER BY stage").fetchall()
    finally:
        connection.close()


def validate(live=False):
    started = invoke("start", "--question", "Investigate synthetic worker initialization")
    run_id, digest = started["run_id"], started["report_sha256"]
    assert started["status"] == "awaiting_approval" and not started["published"]
    before = calls(run_id)
    reopened = invoke("status", "--run-id", run_id)
    assert reopened["report_sha256"] == digest
    invoke("approve", "--run-id", run_id, "--report-sha256", "wrong", successful=False)
    assert not (RUNS / run_id / "approved-report.json").exists()
    completed = invoke("approve", "--run-id", run_id, "--report-sha256", digest)
    assert completed["status"] == "completed" and completed["published"]
    assert calls(run_id) == before == [("draft", "done"), ("retrieve", "done")]
    assert invoke("status", "--run-id", run_id)["status"] == "completed"
    denied = invoke("start", "--question", "Synthetic rejection check")
    rejected = invoke(
        "reject", "--run-id", denied["run_id"], "--report-sha256", denied["report_sha256"]
    )
    assert rejected["status"] == "rejected" and not rejected["published"]
    report = {
        "mock_fresh_process_resume": True,
        "stale_approval_rejected": True,
        "mock_approved_publication": True,
        "rejection_no_publication": True,
        "no_repeated_paid_nodes_on_review": True,
    }
    if live:
        result = invoke(
            "start",
            "--provider",
            "openai",
            "--budget-microusd",
            "20000",
            "--question",
            "Investigate worker environment error states. Separate observations from hypotheses.",
        )
        assert result["status"] == "awaiting_approval" and not result["published"]
        resumed = invoke("status", "--run-id", result["run_id"])
        assert resumed == result
        engine, index = open_index()
        try:
            source = {str(item.event_id): item for item in index.load_file(manifest().file_id)}
            for item in result["evidence"]:
                actual = source[item["event_id"]]
                assert item["file_sha256"] == actual.file_sha256
                assert item["source_line"] == actual.source_line
                assert item["source_commit"] == actual.source_commit
                assert item["text"] == actual.text.encode()[:1200].decode("utf-8", errors="ignore")
        finally:
            engine.dispose()
        assert calls(result["run_id"]) == [("draft", "done"), ("retrieve", "done")]
        report["live"] = {
            "run_id": result["run_id"],
            "status": result["status"],
            "published": False,
            "report_sha256": result["report_sha256"],
            "citations_verified": len(result["evidence"]),
            "fresh_process_state_equal": True,
            "initial_budget_microusd": 20000,
            "remaining_conservative_microusd": result["remaining_conservative_microusd"],
            "checkpoint_bytes": (RUNS / result["run_id"] / "checkpoints.sqlite").stat().st_size,
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.live)
        save(ROOT / "docs/phase5-validation.json", result)
        print(json.dumps(result, indent=2))
    except Exception:
        print("phase5_validation_failed; sensitive details suppressed")
        raise SystemExit(1) from None
