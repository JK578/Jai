"""Explicit revision-range review and guarded development migrations."""

import argparse
import hashlib
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.base import Script
from alembic.script.revision import RevisionError
from incidentiq.config import load_settings
from incidentiq.infrastructure import vector_type as vector_type
from incidentiq.infrastructure.database import database_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from scripts.migration_catalog import SchemaSafetyStop, pristine, unrelated_fingerprint

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/migrations"
PLAN = DIRECTORY / "0001_incidents.sql"  # Original receipt, retained for compatibility.


def alembic_config() -> Config:
    return Config(str(ROOT / "apps/api/alembic.ini"))


def revisions(source: str, target: str) -> list[Script]:
    scripts = ScriptDirectory.from_config(alembic_config())
    final = scripts.get_revision(target)
    if final is None or final.revision != target:
        raise SchemaSafetyStop("Use explicit revision identifiers")
    try:
        chain = list(reversed(list(scripts.iterate_revisions(target, source))))
    except RevisionError:
        raise SchemaSafetyStop("Source is not an ancestor of target revision") from None
    if not chain:
        raise SchemaSafetyStop("An advancing revision range is required")
    return chain


def migration_sql(source: str, target: str) -> str:
    revisions(source, target)
    output = io.StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.upgrade(config, f"{source}:{target}", sql=True)
    return output.getvalue()


def snapshot(revision: str) -> dict[str, Any]:
    try:
        result = json.loads((DIRECTORY / f"{revision}.schema.json").read_text(encoding="utf-8"))
        script = ScriptDirectory.from_config(alembic_config()).get_revision(revision)
        digest = hashlib.sha256(Path(script.path).read_text(encoding="utf-8").encode()).hexdigest()
        if digest != result["migration_sha256"]:
            raise SchemaSafetyStop("Migration differs from reviewed schema snapshot")
        return result
    except OSError, KeyError, ValueError:
        raise SchemaSafetyStop("Missing or invalid reviewed revision snapshot") from None


def current_revision(connection: Connection) -> str:
    if not inspect(connection).has_table("incidentiq_alembic_version", schema="public"):
        return "base"
    values = connection.scalars(
        text("SELECT version_num FROM public.incidentiq_alembic_version")
    ).all()
    if len(values) != 1:
        raise SchemaSafetyStop("Unexpected migration branch state")
    return values[0]


def index_predicate(value: object) -> str | None:
    if value is None:
        return None
    # The reviewed predicates use only simple equality. Normalize PostgreSQL's
    # deparsed text casts/parentheses without general SQL equivalence assumptions.
    return re.sub(r"[\s()]", "", str(value).replace("::text", ""))


def verify_schema(connection: Connection, revision: str) -> None:
    if current_revision(connection) != revision:
        raise SchemaSafetyStop("Database revision differs from requested source/target")
    if revision == "base":
        pristine(connection)
        return
    reviewed = snapshot(revision)
    for extension, requirement in reviewed.get("extensions", {}).items():
        installed = connection.execute(
            text("""SELECT e.extversion, n.nspname
            FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
            WHERE e.extname=:name"""),
            {"name": extension},
        ).first()
        if installed is None or tuple(installed) != (requirement["version"], requirement["schema"]):
            raise SchemaSafetyStop("Extension differs from reviewed revision prerequisite")
    expected = reviewed["tables"]
    inspector = inspect(connection)
    if sorted(inspector.get_table_names(schema="incidentiq")) != sorted(expected):
        raise SchemaSafetyStop("Unexpected IncidentIQ tables")
    if inspector.get_view_names(schema="incidentiq") or inspector.get_sequence_names(
        schema="incidentiq"
    ):
        raise SchemaSafetyStop("Unexpected IncidentIQ views/sequences")
    for table, shape in expected.items():
        columns = {
            c["name"]: {
                "type": str(c["type"].compile(dialect=connection.dialect)),
                "nullable": c["nullable"],
                "default": c["default"],
            }
            for c in inspector.get_columns(table, schema="incidentiq")
        }
        checks = sorted(
            c["name"] for c in inspector.get_check_constraints(table, schema="incidentiq")
        )
        unique = sorted(
            sorted(c["column_names"])
            for c in inspector.get_unique_constraints(table, schema="incidentiq")
        )
        pk = inspector.get_pk_constraint(table, schema="incidentiq")["constrained_columns"]
        indexes = {
            i["name"]: {
                "columns": i["column_names"],
                "unique": bool(i["unique"]),
                "where": index_predicate(i.get("dialect_options", {}).get("postgresql_where")),
            }
            for i in inspector.get_indexes(table, schema="incidentiq")
            if not i.get("duplicates_constraint")
        }
        foreign = sorted(
            [
                {
                    "columns": f["constrained_columns"],
                    "table": f["referred_table"],
                    "schema": f["referred_schema"],
                    "target": f["referred_columns"],
                    "ondelete": f["options"].get("ondelete"),
                }
                for f in inspector.get_foreign_keys(table, schema="incidentiq")
            ],
            key=str,
        )
        if (
            columns != shape["columns"]
            or checks != shape["checks"]
            or unique != shape["unique"]
            or pk != shape["pk"]
            or indexes != shape["indexes"]
            or foreign != shape["foreign"]
        ):
            raise SchemaSafetyStop("Schema differs from reviewed revision snapshot")
    for table in [f"incidentiq.{t}" for t in expected] + ["public.incidentiq_alembic_version"]:
        if not connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:table)"),
            {"table": table},
        ):
            raise SchemaSafetyStop("Required RLS protection missing")
        if connection.scalar(
            text("""SELECT count(*) FROM pg_class c CROSS JOIN LATERAL
            aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
            LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE c.oid=to_regclass(:table)
            AND (a.grantee=0 OR r.rolname IN ('anon','authenticated'))"""),
            {"table": table},
        ):
            raise SchemaSafetyStop("Unexpected public/Data API grants")
    if connection.scalar(
        text("""SELECT count(*) FROM pg_namespace n CROSS JOIN LATERAL
        aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
        LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='incidentiq'
        AND (a.grantee=0 OR r.rolname IN ('anon','authenticated'))""")
    ):
        raise SchemaSafetyStop("Unexpected schema grants")


def protected_tables(connection: Connection) -> dict[str, str]:
    result = {}
    expected = snapshot(current_revision(connection))["tables"]
    for table in inspect(connection).get_table_names(schema="incidentiq"):
        if table not in expected:
            raise SchemaSafetyStop("Unexpected protected table")
        metadata = inspect(connection)
        structure = {
            "columns": [
                dict(c, type=str(c["type"]))
                for c in metadata.get_columns(table, schema="incidentiq")
            ],
            "checks": metadata.get_check_constraints(table, schema="incidentiq"),
            "indexes": metadata.get_indexes(table, schema="incidentiq"),
            "pk": metadata.get_pk_constraint(table, schema="incidentiq"),
            "foreign": metadata.get_foreign_keys(table, schema="incidentiq"),
        }
        digest = hashlib.sha256(json.dumps(structure, sort_keys=True, default=str).encode())
        quoted = connection.dialect.identifier_preparer.quote(table)
        rows = connection.execute(
            text(
                f"SELECT row_to_json(t)::text FROM incidentiq.{quoted} t "
                "ORDER BY row_to_json(t)::text"
            ).execution_options(stream_results=True)
        )
        for row in rows:
            digest.update(row[0].encode())
            digest.update(b"\n")
        result[table] = digest.hexdigest()
    return result


def inspect_target(connection: Connection, source: str, target: str) -> dict[str, Any]:
    revisions(source, target)
    snapshot(target)
    verify_schema(connection, source)
    if source != "base":
        for table in snapshot(source)["tables"]:
            quoted = connection.dialect.identifier_preparer.quote(table)
            connection.execute(text(f"LOCK TABLE incidentiq.{quoted} IN SHARE MODE"))
    fingerprint, count = unrelated_fingerprint(connection)
    url = connection.engine.url
    identity = hashlib.sha256(
        json.dumps([url.host, url.port, url.database, url.username]).encode()
    ).hexdigest()
    return {
        "source": source,
        "target": target,
        "database_identity_sha256": identity,
        "unrelated_metadata_sha256": fingerprint,
        "unrelated_relation_count": count,
        "protected_tables": protected_tables(connection) if source != "base" else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["plan", "inspect", "upgrade", "status"])
    parser.add_argument("--from-revision", required=True)
    parser.add_argument("--to-revision", required=True)
    parser.add_argument("--reviewed-sha256")
    args = parser.parse_args()
    logging.getLogger("alembic").setLevel(logging.CRITICAL)
    source, target = args.from_revision, args.to_revision
    for revision in revisions(source, target):
        snapshot(revision.revision)
    sql = migration_sql(source, target)
    digest = hashlib.sha256(sql.encode()).hexdigest()
    plan = DIRECTORY / f"{target}.sql"
    report = DIRECTORY / f"{source}--{target}.inspection.json"
    if args.operation == "plan":
        if plan.exists() and plan.read_text(encoding="utf-8") != sql:
            raise SchemaSafetyStop("Existing SQL receipt differs; history must not be overwritten")
        plan.write_text(sql, encoding="utf-8")
        print(f"PASS: offline SQL generated; SHA256 {digest}")
        return
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise SchemaSafetyStop("Only a configured development database is allowed")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout='5000ms'"))
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            connection.execute(text("SET LOCAL timezone='UTC'"))
            if args.operation == "status":
                actual = current_revision(connection)
                verify_schema(connection, actual)
                print(json.dumps({"revision": actual, "schema_verified": True}))
                return
            connection.execute(text("SELECT pg_advisory_xact_lock(1938461)"))
            before = inspect_target(connection, source, target)
            if args.operation == "inspect":
                report.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
                print("PASS: source schema inspected; no migration applied")
                return
            if (
                args.reviewed_sha256 != digest
                or not plan.exists()
                or plan.read_text(encoding="utf-8") != sql
                or not report.exists()
                or json.loads(report.read_text(encoding="utf-8")) != before
            ):
                raise SchemaSafetyStop(
                    "SQL hash or database baseline differs; inspect/review again"
                )
            config = alembic_config()
            config.attributes.update(connection=connection, schema_reviewed=True)
            command.upgrade(config, target)
            verify_schema(connection, target)
            after = protected_tables(connection)
            if any(
                after.get(table) != value for table, value in before["protected_tables"].items()
            ):
                raise SchemaSafetyStop("Existing data/structure changed; migration rolled back")
            if unrelated_fingerprint(connection)[0] != before["unrelated_metadata_sha256"]:
                raise SchemaSafetyStop("Unrelated metadata changed; migration rolled back")
        print("PASS: reviewed migration applied; protected data/metadata preserved")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except SchemaSafetyStop as error:
        print(f"STOP: {error}")
        raise SystemExit(1) from None
    except Exception:
        print("STOP: database operation failed; sensitive details suppressed")
        raise SystemExit(1) from None
