"""Read-only current schema, source-data, retrieval and runtime privilege receipt."""

import json

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import Database
from incidentiq.infrastructure.log_source import manifest
from pydantic import SecretStr
from sqlalchemy import text

from scripts.manage_database import DIRECTORY, protected_tables, verify_schema
from scripts.migration_catalog import unrelated_fingerprint
from scripts.retrieval_cli import ROOT, open_index, save, status


def main():
    engine, _ = open_index()
    try:
        baseline = json.loads(
            (DIRECTORY / "0003_retrieval--0004_access.inspection.json").read_text()
        )
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL timezone='UTC'"))
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            verify_schema(connection, "0004_access")
            actual = protected_tables(connection)
            assert all(
                actual[name] == value for name, value in baseline["protected_tables"].items()
            )
            assert unrelated_fingerprint(connection)[0] == baseline["unrelated_metadata_sha256"]
        index = status(engine, manifest().file_id)
        historical = json.loads((ROOT / "docs/phase5-integrity.json").read_text())
        assert index["documents"] == index["source_events"] == 2000
        assert index["index_sha256"] == historical["index"]["index_sha256"]
        settings = load_settings()
        assert settings.auth_enabled and isinstance(settings.runtime_database_url, SecretStr)
        runtime = Database(settings.runtime_database_url)
        try:
            assert runtime.ready() and runtime.restricted()
        finally:
            runtime.close()
        result = {
            "revision": "0004_access",
            "exact_schema_and_policies_verified": True,
            "original_tables_unchanged": True,
            "unrelated_metadata_unchanged": True,
            "restricted_runtime_verified": True,
            "index": index,
        }
        save(ROOT / "docs/access-integrity.json", result)
        print(json.dumps(result, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"access_integrity_failed: {type(error).__name__}; details suppressed")
        raise SystemExit(1) from None
