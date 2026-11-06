"""Final read-only schema, protected-data and persistence/resource verification."""

import json

from incidentiq.infrastructure.log_source import manifest
from sqlalchemy import text

from scripts.manage_database import DIRECTORY, protected_tables, verify_schema
from scripts.migration_catalog import unrelated_fingerprint
from scripts.retrieval_cli import ROOT, open_index, save, status


def validate():
    engine, _ = open_index()
    try:
        baseline = json.loads((DIRECTORY / "0002_logs--0003_retrieval.inspection.json").read_text())
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL timezone='UTC'"))
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            verify_schema(connection, "0003_retrieval")
            actual = protected_tables(connection)
            assert all(
                actual[name] == digest for name, digest in baseline["protected_tables"].items()
            )
            assert unrelated_fingerprint(connection)[0] == baseline["unrelated_metadata_sha256"]
        first = json.loads((ROOT / "docs/phase4-restart-a.json").read_text())
        second = json.loads((ROOT / "docs/phase4-restart-b.json").read_text())
        assert first["documents"] == second["documents"] == 2000
        assert first["index_sha256"] == second["index_sha256"]
        replay = json.loads((ROOT / "docs/phase4-replay.json").read_text())
        assert replay["index_unchanged"] and replay["new_embeddings"] == 0
        assert replay["before"]["index_sha256"] == replay["after"]["index_sha256"]
        indexing = json.loads((ROOT / "docs/phase4-indexing.json").read_text())
        assert indexing["worker_peak_minus_baseline_bytes"] < 100 * 1024**2
        current = status(engine, manifest().file_id)
        assert current["documents"] == current["source_events"] == 2000
        assert current["retrieval_storage_bytes"] < 10 * 1024**2
        assert current["index_sha256"] == first["index_sha256"]
        return {
            "schema_verified": True,
            "protected_source_tables_unchanged": True,
            "unrelated_relation_metadata_unchanged": True,
            "replay_no_api_calls": True,
            "fresh_process_persistence_passed": True,
            "index": current,
            "storage_below_10mib": True,
            "worker_increment_below_100mib": True,
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        result = validate()
        save(ROOT / "docs/phase4-final-verification.json", result)
        print(json.dumps(result, indent=2))
    except Exception:
        print("retrieval_verification_failed; details suppressed")
        raise SystemExit(1) from None
