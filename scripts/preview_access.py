"""Rollback-only security DDL preview; capture canonical RLS expressions for review."""

import json
from uuid import uuid4

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import database_engine
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from scripts.manage_database import (
    DIRECTORY,
    migration_sql,
    policy_definitions,
    protected_tables,
    verify_schema,
)
from scripts.migration_catalog import unrelated_fingerprint


def prove_rls(connection):
    """Exercise real runtime role policies; roll all test mappings and rows back."""
    tenant_a, tenant_b, new_id = uuid4(), uuid4(), uuid4()
    fixture = connection.begin_nested()
    try:
        incident_id = connection.scalar(text("SELECT id FROM incidentiq.incidents LIMIT 1"))
        file_id = connection.scalar(text("SELECT id FROM incidentiq.log_files LIMIT 1"))
        for kind, identity in (("incident", incident_id), ("file", file_id)):
            connection.execute(
                text("INSERT INTO incidentiq.resource_owners VALUES (:kind,:id,:tenant)"),
                {"kind": kind, "id": identity, "tenant": tenant_a},
            )
        connection.execute(text("SET LOCAL ROLE incidentiq_runtime"))
        for tenant, expected in ((tenant_a, 2000), (tenant_b, 0)):
            connection.execute(
                text("SELECT set_config('incidentiq.tenant_id', :id, true)"), {"id": str(tenant)}
            )
            assert connection.scalar(text("SELECT count(*) FROM incidentiq.log_events")) == expected
            assert (
                connection.scalar(text("SELECT count(*) FROM incidentiq.retrieval_documents"))
                == expected
            )
            assert connection.scalar(text("SELECT count(*) FROM incidentiq.incidents")) == int(
                expected > 0
            )
            assert connection.scalar(text("SELECT count(*) FROM incidentiq.log_datasets")) == int(
                expected > 0
            )
        connection.execute(
            text("INSERT INTO incidentiq.resource_owners VALUES ('incident',:id,:tenant)"),
            {"id": new_id, "tenant": tenant_b},
        )
        connection.execute(
            text("""INSERT INTO incidentiq.incidents VALUES
            (:id,'RLS test','rollback only','low','open','test',
             CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
            {"id": new_id},
        )
        assert connection.scalar(text("SELECT count(*) FROM incidentiq.incidents")) == 1
        for statement in (
            "DELETE FROM incidentiq.log_events WHERE false",
            "UPDATE incidentiq.incidents SET title='blocked' WHERE false",
            "CREATE TABLE incidentiq.forbidden (id int)",
        ):
            attempt = connection.begin_nested()
            try:
                connection.execute(text(statement))
            except DBAPIError as error:
                assert error.orig.sqlstate == "42501"
            else:
                raise AssertionError("Runtime role received an unauthorized privilege")
            finally:
                attempt.rollback()
    finally:
        fixture.rollback()


def preview():
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise ValueError("Development database required")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
                connection.execute(text("SET LOCAL lock_timeout='5000ms'"))
                connection.execute(text("SET LOCAL timezone='UTC'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(1938461)"))
                verify_schema(connection, "0003_retrieval")
                before = protected_tables(connection)
                unrelated = unrelated_fingerprint(connection)
                sql = migration_sql("0003_retrieval", "0004_access")
                body = sql.split("BEGIN;", 1)[1].rsplit("COMMIT;", 1)[0]
                connection.exec_driver_sql(body)
                # Preview-only membership, reverted with the whole DDL transaction.
                connection.execute(text("GRANT incidentiq_runtime TO CURRENT_USER"))
                policies = policy_definitions(connection)
                path = DIRECTORY / "0004_access.schema.json"
                reviewed = json.loads(path.read_text())
                reviewed["policies"] = policies
                path.write_text(json.dumps(reviewed, indent=2) + "\n", encoding="utf-8")
                verify_schema(connection, "0004_access")
                prove_rls(connection)
                after = protected_tables(connection)
                assert all(after[name] == digest for name, digest in before.items())
                assert unrelated_fingerprint(connection) == unrelated
            finally:
                transaction.rollback()
            verify_schema(connection, "0003_retrieval")
            assert not connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='incidentiq_runtime')")
            )
        print("PASS: security preview rolled back; policies captured; source rows preserved")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        preview()
    except Exception as error:
        import traceback

        print("Security preview failed:", type(error).__name__)
        print("SQL state:", getattr(getattr(error, "orig", None), "sqlstate", None))
        for frame in traceback.extract_tb(error.__traceback__):
            if frame.name in ("preview", "prove_rls", "verify_schema"):
                print(frame.name, frame.lineno)
        raise SystemExit(1) from None
