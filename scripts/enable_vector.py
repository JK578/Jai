"""Apply the explicitly approved pgvector prerequisite with integrity checks."""

import hashlib
import json

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import database_engine
from sqlalchemy import text

from scripts.manage_database import DIRECTORY, inspect_target, protected_tables, verify_schema
from scripts.migration_catalog import SchemaSafetyStop, unrelated_fingerprint

REVIEWED = "81164720ba88927d17bb2df2478747432692c6be5467d54c80ff27670787efa4"


def enable() -> dict:
    sql = (DIRECTORY / "0003_vector_prerequisite.sql").read_text(encoding="utf-8")
    if hashlib.sha256(sql.encode()).hexdigest() != REVIEWED:
        raise SchemaSafetyStop("Extension SQL differs from the reviewed prerequisite")
    # The engine owns BEGIN/COMMIT so postflight verification remains in the same transaction.
    _, body = sql.split("BEGIN;\n", 1)
    body, tail = body.rsplit("COMMIT;", 1)
    if tail.strip():
        raise SchemaSafetyStop("Unexpected SQL after transaction boundary")
    baseline = json.loads((DIRECTORY / "0002_logs--0003_retrieval.inspection.json").read_text())
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise SchemaSafetyStop("Configured development database required")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            connection.execute(text("SET LOCAL lock_timeout='5000ms'"))
            connection.execute(text("SET LOCAL timezone='UTC'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(1938461)"))
            before = inspect_target(connection, "0002_logs", "0003_retrieval")
            if before != baseline:
                raise SchemaSafetyStop("Database target or baseline changed; inspect again")
            available = connection.scalar(
                text("""SELECT EXISTS (
                SELECT 1 FROM pg_available_extension_versions WHERE name='vector'
                AND version='0.8.2')""")
            )
            if not available:
                raise SchemaSafetyStop("Reviewed vector version unavailable")
            connection.exec_driver_sql(body)
            installed = connection.execute(
                text("""SELECT e.extversion, n.nspname
                FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
                WHERE e.extname='vector'""")
            ).first()
            if installed is None or tuple(installed) != ("0.8.2", "extensions"):
                raise SchemaSafetyStop("Unexpected installed extension; rolling back")
            verify_schema(connection, "0002_logs")
            if protected_tables(connection) != before["protected_tables"]:
                raise SchemaSafetyStop("Protected data changed; rolling back")
            if unrelated_fingerprint(connection)[0] != before["unrelated_metadata_sha256"]:
                raise SchemaSafetyStop("Unrelated relation metadata changed; rolling back")
        return {
            "vector_version": "0.8.2",
            "vector_schema": "extensions",
            "revision": "0002_logs",
            "migration_0003_applied": False,
            "reviewed_sql_sha256": REVIEWED,
            "protected_data_unchanged": True,
            "unrelated_relation_metadata_unchanged": True,
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        receipt = enable()
        (DIRECTORY / "0003_vector_enabled.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, indent=2))
    except SchemaSafetyStop as error:
        print(f"STOP: {error}")
        raise SystemExit(1) from None
    except Exception:
        print("STOP: extension operation failed; sensitive details suppressed")
        raise SystemExit(1) from None
