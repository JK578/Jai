"""Local development checkpoint helpers; no Supabase DDL or external tool execution."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from incidentiq.domain.investigations import InvestigationFailure


class CallJournal:
    def __init__(self, path: Path):
        self.path = path
        with sqlite3.connect(path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS calls (
                stage TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL,
                result TEXT, PRIMARY KEY(stage, attempt))""")

    def call(self, stage, attempt, function):
        if stage not in {"retrieve", "draft"} or attempt not in (0, 1):
            raise InvestigationFailure("investigation_call_invalid")
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                "SELECT state, result FROM calls WHERE stage=? AND attempt=?", (stage, attempt)
            ).fetchone()
            if existing:
                if existing[0] == "done":
                    return json.loads(existing[1])
                code = (
                    "investigation_call_uncertain"
                    if existing[0] == "pending"
                    else f"investigation_{stage}_failed"
                )
                raise InvestigationFailure(code)
            connection.execute("INSERT INTO calls VALUES (?, ?, 'pending', NULL)", (stage, attempt))
        try:
            result = function()
            encoded = json.dumps(result, allow_nan=False)
            if len(encoded.encode()) > 32000:
                raise ValueError
        except Exception:
            with sqlite3.connect(self.path) as connection:
                connection.execute(
                    "UPDATE calls SET state='failed' WHERE stage=? AND attempt=?", (stage, attempt)
                )
            raise InvestigationFailure(f"investigation_{stage}_failed") from None
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE calls SET state='done', result=? WHERE stage=? AND attempt=?",
                (encoded, stage, attempt),
            )
        return result


@contextmanager
def run_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise InvestigationFailure("investigation_run_busy") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def publish_local(directory: Path, report: dict):
    target = directory / "approved-report.json"
    if target.exists():
        if json.loads(target.read_text(encoding="utf-8")) != report:
            raise InvestigationFailure("investigation_report_conflict")
        return
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
