"""Atomic daily reservations for untrusted HTTP callers; no automatic refunds."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from incidentiq.domain.access import AccessDenied


class UsageBudget:
    def __init__(self, path: Path, limit=100000):
        self.path, self.limit = path, limit
        path.parent.mkdir(parents=True, exist_ok=True)

    def reserve(self, user_id, amount):
        if type(amount) is not int or not 0 < amount <= self.limit:
            raise AccessDenied("daily_budget_exceeded")
        day = datetime.now(UTC).date().isoformat()
        with closing(sqlite3.connect(self.path, timeout=2)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS usage (user_id TEXT, day TEXT, "
                "spent INTEGER, PRIMARY KEY(user_id,day))"
            )
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT spent FROM usage WHERE user_id=? AND day=?", (str(user_id), day)
            ).fetchone()
            used = row[0] if row else 0
            if used + amount > self.limit:
                raise AccessDenied("daily_budget_exceeded")
            connection.execute(
                "INSERT INTO usage VALUES (?,?,?) ON CONFLICT(user_id,day) "
                "DO UPDATE SET spent=excluded.spent",
                (str(user_id), day, used + amount),
            )
        return self.limit - used - amount
