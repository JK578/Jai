"""Temporary-safe runtime checks: fixed categories only, never connection details."""

import json
from pathlib import Path

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import Database, database_engine
from pydantic import SecretStr
from sqlalchemy import text


def diagnose():
    settings = load_settings()
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.connect() as connection:
            print(
                "Runtime role exists:",
                connection.scalar(
                    text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='incidentiq_app')")
                ),
            )
            print(
                "Ownership mappings:",
                connection.scalar(text("SELECT count(*) FROM incidentiq.resource_owners")),
            )
    finally:
        engine.dispose()
    secret = SecretStr(Path(".cache/access/runtime-url.pending").read_text())
    runtime = Database(secret)
    try:
        with runtime.engine.connect() as connection:
            print("Connection:", connection.scalar(text("SELECT 1")) == 1)
            print(
                "Role flags:",
                list(
                    connection.execute(
                        text("""SELECT rolsuper,
                rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles
                WHERE rolname=current_user""")
                    ).first()
                ),
            )
        print("Restricted:", runtime.restricted(), "Ready:", runtime.ready())
    except Exception as error:
        message = str(error).lower()
        labels = [
            word
            for word in (
                "certificate verify",
                "password authentication",
                "tenant or user not found",
                "permission denied",
                "network",
                "timeout",
            )
            if word in message
        ]
        print(json.dumps({"category": labels or [type(error).__name__]}))
    finally:
        runtime.close()


if __name__ == "__main__":
    diagnose()
