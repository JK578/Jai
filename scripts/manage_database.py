"""Inspect, generate SQL, and apply only the reviewed initial development migration."""

import argparse
import hashlib
import io
import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from incidentiq.config import load_settings
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.models import IncidentRow
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/migrations/0001_incidents.sql"
REPORT = ROOT / "docs/migrations/inspection.json"


class SchemaSafetyStop(RuntimeError):
    """Only fixed, non-sensitive safety messages are safe to print."""


def alembic_config() -> Config:
    return Config(str(ROOT / "apps/api/alembic.ini"))


def migration_sql() -> str:
    output = io.StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    return output.getvalue()


def unrelated_fingerprint(connection: Connection) -> tuple[str, int]:
    # Metadata only, never table contents. Capture columns, defaults, constraints, indexes and ACLs.
    rows = connection.execute(
        text("""
        SELECT n.nspname, c.relname, c.relkind, c.relrowsecurity, c.relacl::text,
          (SELECT string_agg(a.attname || ':' || a.atttypid::text || ':' || a.atttypmod::text
             || ':' || a.attnotnull::text || ':' || coalesce(pg_get_expr(d.adbin,d.adrelid),''),
             ',' ORDER BY a.attnum)
           FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
           WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
          (SELECT string_agg(pg_get_constraintdef(k.oid),',' ORDER BY k.conname)
           FROM pg_constraint k WHERE k.conrelid=c.oid),
          (SELECT string_agg(indexdef,',' ORDER BY indexname) FROM pg_indexes i
           WHERE i.schemaname=n.nspname AND i.tablename=c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname NOT IN ('information_schema','incidentiq')
          AND NOT (n.nspname='public' AND c.relname LIKE 'incidentiq_alembic_version%')
        ORDER BY n.nspname,c.relname
    """)
    ).all()
    serialized = json.dumps([list(row) for row in rows], default=str, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest(), len(rows)


def pristine(connection: Connection) -> None:
    inspector = inspect(connection)
    if "incidentiq" in inspector.get_schema_names():
        raise SchemaSafetyStop("Unexpected existing incidentiq schema; stopped without migration")
    if inspector.has_table("incidentiq_alembic_version", schema="public"):
        raise SchemaSafetyStop("Existing migration tracking state; initial-only guard stopped")
    if inspector.has_table("incidents", schema="public"):
        raise SchemaSafetyStop("Unexpected public.incidents table; stopped for schema review")


def inspect_target(connection: Connection) -> dict[str, object]:
    pristine(connection)
    fingerprint, count = unrelated_fingerprint(connection)
    return {
        "initial_schema_pristine": True,
        "unrelated_relation_count": count,
        "unrelated_metadata_sha256": fingerprint,
        "planned_objects": [
            "incidentiq schema",
            "incidentiq.incidents",
            "public.incidentiq_alembic_version",
        ],
    }


def verify_applied_schema(connection: Connection) -> dict[str, object]:
    inspector = inspect(connection)
    if inspector.get_table_names(schema="incidentiq") != ["incidents"]:
        raise SchemaSafetyStop("Unexpected IncidentIQ tables; stopped for schema review")
    columns = inspector.get_columns("incidents", schema="incidentiq")
    expected = IncidentRow.__table__.columns
    if {column["name"] for column in columns} != {column.name for column in expected}:
        raise SchemaSafetyStop("Incident columns differ from model; stopped for schema review")
    for column in columns:
        model = expected[column["name"]]
        if column["nullable"] != model.nullable or (
            column["type"].compile(dialect=connection.dialect)
            != model.type.compile(dialect=connection.dialect)
        ):
            raise SchemaSafetyStop("Incident column types/nullability differ from model")
    constraints = inspector.get_check_constraints("incidents", schema="incidentiq")
    required = {item.name for item in IncidentRow.__table__.constraints if item.name}
    if {item["name"] for item in constraints} != required:
        raise SchemaSafetyStop("Incident constraints differ from model")
    if inspector.get_pk_constraint("incidents", schema="incidentiq")["constrained_columns"] != [
        "id"
    ]:
        raise SchemaSafetyStop("Incident primary key differs from model")
    indexes = inspector.get_indexes("incidents", schema="incidentiq")
    if not any(
        item["name"] == "ix_incidents_created_id" and item["column_names"] == ["created_at", "id"]
        for item in indexes
    ):
        raise SchemaSafetyStop("Incident ordering index is missing")
    revision = connection.scalar(text("SELECT version_num FROM public.incidentiq_alembic_version"))
    if revision != "0001_incidents":
        raise SchemaSafetyStop("Unexpected applied migration revision")
    security = (
        connection.execute(
            text("""
        SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE (n.nspname='incidentiq' AND c.relname='incidents')
           OR (n.nspname='public' AND c.relname='incidentiq_alembic_version')
    """)
        )
        .scalars()
        .all()
    )
    if len(security) != 2 or not all(security):
        raise SchemaSafetyStop("Expected RLS protection is missing")
    for role in ("anon", "authenticated"):
        exposed = connection.scalar(
            text("""
            SELECT has_schema_privilege(:role,'incidentiq','USAGE')
               OR has_table_privilege(:role,'incidentiq.incidents','SELECT,INSERT,UPDATE,DELETE')
               OR has_table_privilege(:role,'public.incidentiq_alembic_version',
                                      'SELECT,INSERT,UPDATE,DELETE')
        """),
            {"role": role},
        )
        if exposed:
            raise SchemaSafetyStop("Unexpected Data API role grants; stopped for security review")
    fingerprint, count = unrelated_fingerprint(connection)
    baseline = json.loads(REPORT.read_text(encoding="utf-8"))
    if fingerprint != baseline["unrelated_metadata_sha256"]:
        raise SchemaSafetyStop("Unrelated metadata differs from preflight baseline")
    return {
        "revision": revision,
        "columns": len(columns),
        "check_constraints": len(constraints),
        "primary_key": "id",
        "ordering_index_verified": True,
        "rls_enabled": True,
        "data_api_grants_revoked": True,
        "unrelated_relation_count": count,
        "unrelated_metadata_unchanged": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["plan", "inspect", "upgrade", "status"])
    parser.add_argument("--reviewed-sha256")
    args = parser.parse_args()
    logging.getLogger("alembic").setLevel(logging.CRITICAL)
    sql = migration_sql()
    digest = hashlib.sha256(sql.encode()).hexdigest()
    if args.operation == "plan":
        PLAN.parent.mkdir(parents=True, exist_ok=True)
        PLAN.write_text(sql, encoding="utf-8")
        print(f"Migration SQL generated: {PLAN.relative_to(ROOT)}")
        print(f"Review SHA256: {digest}")
        return
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise SchemaSafetyStop("Only a configured development database is allowed")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5000ms'"))
            connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            if args.operation == "status":
                result = verify_applied_schema(connection)
                receipt = ROOT / "docs/migrations/applied.json"
                receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(result, indent=2))
                return
            if args.operation == "inspect":
                result = inspect_target(connection)
                REPORT.parent.mkdir(parents=True, exist_ok=True)
                REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(result, indent=2))
                return
            if (
                args.reviewed_sha256 != digest
                or not PLAN.exists()
                or PLAN.read_text(encoding="utf-8") != sql
            ):
                raise SchemaSafetyStop("Generated migration SQL does not match reviewed hash/file")
            if not REPORT.exists():
                raise SchemaSafetyStop("Run schema inspection before migration")
            connection.execute(text("SELECT pg_advisory_xact_lock(1938461)"))
            before = inspect_target(connection)
            if before != json.loads(REPORT.read_text(encoding="utf-8")):
                raise SchemaSafetyStop("Schema changed since inspection; stopped without migration")
            config = alembic_config()
            config.attributes.update(connection=connection, schema_reviewed=True)
            command.upgrade(config, "head")
            fingerprint, _ = unrelated_fingerprint(connection)
            if fingerprint != before["unrelated_metadata_sha256"]:
                raise SchemaSafetyStop("Unrelated schema metadata changed; migration rolled back")
            revision = connection.scalar(
                text("SELECT version_num FROM public.incidentiq_alembic_version")
            )
            if revision != "0001_incidents":
                raise SchemaSafetyStop("Unexpected applied revision; migration rolled back")
        print("PASS: reviewed initial migration applied; unrelated metadata unchanged")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SchemaSafetyStop as error:
        # Only our fixed messages are emitted. Never print driver/SQLAlchemy exceptions.
        print(f"STOP: {error}")
        raise SystemExit(1) from None
    except Exception:
        print("STOP: database operation failed; credentials and internal details suppressed")
        raise SystemExit(1) from None
