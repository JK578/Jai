"""Controlled Phase 2B evidence. Errors never include connection or SQL details."""

import argparse
import hashlib
import json
from pathlib import Path

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import database_engine
from sqlalchemy import inspect, text

from scripts.manage_database import (
    DIRECTORY,
    current_revision,
    inspect_target,
    migration_sql,
    protected_tables,
    verify_schema,
)
from scripts.migration_catalog import SchemaSafetyStop, unrelated_fingerprint

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/phase2b-live-evidence"
SQL_DIGEST = "d3f59a42af151a26995248cd2c1604ba8bcaa5ef30339fbf528dd75432618094"


def incident_integrity(connection) -> dict:
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(
        text("SELECT row_to_json(t)::text FROM incidentiq.incidents t ORDER BY id")
    ):
        digest.update(row[0].encode())
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def log_storage(connection) -> int:
    return int(
        connection.scalar(
            text("""
        SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='incidentiq' AND c.relkind='r' AND c.relname IN
          ('log_datasets','log_files','log_ingestion_runs','log_events','log_ingestion_errors')
    """)
        )
    )


def save(name: str, result: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{name}.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preflight", "postmigration", "final"])
    args = parser.parse_args()
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise SchemaSafetyStop("Configured development database required")
    engine = database_engine(settings.database_url, pooled=False)
    # Match the project previously identified by the user; never output the endpoint or user.
    reference = "ngwondsdwnbmvawyszey"
    url = engine.url
    if not (
        (url.host == f"db.{reference}.supabase.co")
        or (
            (url.host or "").endswith(".pooler.supabase.com")
            and url.username == f"postgres.{reference}"
        )
    ):
        engine.dispose()
        raise SchemaSafetyStop("Configured Supabase project differs from approved project")
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            connection.execute(text("SET LOCAL lock_timeout='5000ms'"))
            connection.execute(text("SET LOCAL timezone='UTC'"))
            if (
                connection.scalar(text("SELECT 1")) != 1
                or not connection.connection.driver_connection.pgconn.ssl_in_use
            ):
                raise SchemaSafetyStop("Connectivity or SSL check failed")
            revision = current_revision(connection)
            expected = "0001_incidents" if args.operation == "preflight" else "0002_logs"
            if revision != expected:
                raise SchemaSafetyStop("Unexpected database revision; stopped without migration")
            verify_schema(connection, expected)
            incidents = incident_integrity(connection)
            unrelated, relation_count = unrelated_fingerprint(connection)
            result = {
                "development_project_match": True,
                "ssl": True,
                "revision": revision,
                "incident_integrity": incidents,
                "unrelated_metadata_sha256": unrelated,
                "unrelated_relation_count": relation_count,
                "tables": inspect(connection).get_table_names(schema="incidentiq"),
                "log_storage_bytes": log_storage(connection),
            }
            if args.operation == "preflight":
                sql = migration_sql("0001_incidents", "0002_logs")
                if (
                    hashlib.sha256(sql.encode()).hexdigest() != SQL_DIGEST
                    or sql != (DIRECTORY / "0002_logs.sql").read_text(encoding="utf-8")
                    or sql.count("CREATE TABLE incidentiq.") != 5
                    or "DROP " in sql.upper()
                    or "incidentiq.incidents" in sql
                ):
                    raise SchemaSafetyStop("Migration SQL differs from reviewed additive plan")
                initial = json.loads((DIRECTORY / "inspection.json").read_text(encoding="utf-8"))
                if unrelated != initial["unrelated_metadata_sha256"]:
                    raise SchemaSafetyStop("Unrelated schema differs from historical baseline")
                baseline = inspect_target(connection, "0001_incidents", "0002_logs")
                (DIRECTORY / "0001_incidents--0002_logs.inspection.json").write_text(
                    json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
                )
                result["reviewed_sql_sha256"] = SQL_DIGEST
                result["protected_tables"] = protected_tables(connection)
            else:
                baseline = json.loads((EVIDENCE / "preflight.json").read_text(encoding="utf-8"))
                if (
                    incidents != baseline["incident_integrity"]
                    or unrelated != baseline["unrelated_metadata_sha256"]
                ):
                    raise SchemaSafetyStop("Incident integrity or unrelated metadata changed")
                result["incident_integrity_unchanged"] = True
                result["unrelated_metadata_unchanged"] = True
            save(args.operation, result)
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SchemaSafetyStop as error:
        print(f"STOP: {error}")
        raise SystemExit(1) from None
    except Exception:
        print("STOP: validation failed; sensitive details suppressed")
        raise SystemExit(1) from None
