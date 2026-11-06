import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from alembic.util.exc import CommandError
from incidentiq.config import Settings
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from scripts import manage_database
from scripts.manage_database import (
    DIRECTORY,
    SchemaSafetyStop,
    migration_sql,
    revisions,
    snapshot,
    verify_schema,
)


def test_applied_0001_is_unchanged_and_its_sql_is_reproducible():
    path = Path("apps/api/migrations/versions/0001_incidents.py")
    assert hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest() == (
        "2924d25751840d0b269eea9fbfd4571f6b53c70663b417758d6353de0664db61"
    )
    assert migration_sql("base", "0001_incidents") == (DIRECTORY / "0001_incidents.sql").read_text(
        encoding="utf-8"
    )


def test_additive_0002_sql_range_is_reviewed_and_does_not_touch_incidents():
    sql = migration_sql("0001_incidents", "0002_logs")
    assert sql == (DIRECTORY / "0002_logs.sql").read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE incidentiq.") == 5
    assert sql.count("ENABLE ROW LEVEL SECURITY") == 5
    assert "DROP " not in sql.upper() and "incidentiq.incidents" not in sql
    assert "UPDATE public.incidentiq_alembic_version" in sql
    assert "WHERE" in sql and "uq_log_one_worker" in sql
    assert [r.revision for r in revisions("base", "0002_logs")] == ["0001_incidents", "0002_logs"]
    assert set(snapshot("0001_incidents")["tables"]) == {"incidents"}
    assert len(snapshot("0002_logs")["tables"]) == 6


def test_retrieval_migration_is_additive_and_prerequisite_is_separate():
    sql = migration_sql("0002_logs", "0003_retrieval")
    assert sql == (DIRECTORY / "0003_retrieval.sql").read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE incidentiq.") == 1
    assert "CREATE EXTENSION" not in sql.upper()
    assert "DROP " not in sql.upper()
    assert "ALTER TABLE incidentiq.log_" not in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL" in sql
    assert "extensions.vector(512)" in sql
    assert "ON DELETE RESTRICT" in sql
    before = snapshot("0002_logs")["tables"]
    after = snapshot("0003_retrieval")
    assert {name: after["tables"][name] for name in before} == before
    assert set(after["tables"]) - set(before) == {"retrieval_documents"}
    assert after["extensions"] == {"vector": {"schema": "extensions", "version": "0.8.2"}}


@pytest.mark.parametrize("installed", [None, ("0.8.2", "public"), ("0.7.0", "extensions")])
def test_retrieval_revision_requires_exact_extension(monkeypatch, installed):
    connection = MagicMock()
    connection.execute.return_value.first.return_value = installed
    monkeypatch.setattr(manage_database, "current_revision", lambda c: "0003_retrieval")
    with pytest.raises(SchemaSafetyStop, match="Extension differs"):
        verify_schema(connection, "0003_retrieval")


def test_vector_reflection_retains_dimensions():
    from incidentiq.infrastructure.vector_type import Vector

    assert str(Vector(512).compile(dialect=postgresql.dialect())) == "VECTOR(512)"
    from types import SimpleNamespace

    dialect = postgresql.dialect()
    for name in ("vector(512)", "extensions.vector(512)"):
        reflected = dialect._reflect_type(
            name, SimpleNamespace(enums={}, domains={}), "embedding", None
        )
        assert str(reflected.compile(dialect=dialect)) == "VECTOR(512)"


@pytest.mark.parametrize(
    "source,target", [("0002_logs", "0001_incidents"), ("0002_logs", "0002_logs"), ("base", "head")]
)
def test_invalid_or_ambiguous_revision_range_rejected(source, target):
    with pytest.raises((SchemaSafetyStop, CommandError)):
        revisions(source, target)


def test_status_uses_current_revision_snapshot_not_repository_head():
    expected = snapshot("0001_incidents")["tables"]["incidents"]
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["incidents"]
    inspector.get_view_names.return_value = []
    inspector.get_sequence_names.return_value = []
    columns = []
    for name, shape in expected["columns"].items():
        kind = MagicMock()
        kind.compile.return_value = shape["type"]
        columns.append({"name": name, "type": kind, "nullable": shape["nullable"], "default": None})
    inspector.get_columns.return_value = columns
    inspector.get_check_constraints.return_value = [{"name": name} for name in expected["checks"]]
    inspector.get_unique_constraints.return_value = []
    inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    inspector.get_indexes.return_value = [
        {"name": name, "column_names": shape["columns"], "unique": shape["unique"]}
        for name, shape in expected["indexes"].items()
    ]
    inspector.get_foreign_keys.return_value = []
    connection = MagicMock(dialect=postgresql.dialect())
    connection.scalar.side_effect = [True, 0, True, 0, 0]
    with (
        patch("scripts.manage_database.current_revision", return_value="0001_incidents"),
        patch("scripts.manage_database.inspect", return_value=inspector),
    ):
        verify_schema(connection, "0001_incidents")
        inspector.get_table_names.return_value = ["incidents", "unexpected"]
        with pytest.raises(SchemaSafetyStop):
            verify_schema(connection, "0001_incidents")


@pytest.mark.parametrize("failure", ["hash", "baseline", "protected_data", "unrelated_metadata"])
def test_upgrade_stops_or_rolls_back_on_review_mismatch(tmp_path, monkeypatch, failure):
    sql = migration_sql("0001_incidents", "0002_logs")
    digest = hashlib.sha256(sql.encode()).hexdigest()
    before = {"protected_tables": {"incidents": "before"}, "unrelated_metadata_sha256": "baseline"}
    (tmp_path / "0002_logs.sql").write_text(sql, encoding="utf-8")
    receipt = {**before, "changed": True} if failure == "baseline" else before
    (tmp_path / "0001_incidents--0002_logs.inspection.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    monkeypatch.setattr(manage_database, "DIRECTORY", tmp_path)
    monkeypatch.setattr(manage_database, "snapshot", lambda _revision: {})
    monkeypatch.setattr(
        manage_database, "load_settings", lambda: Settings(database_url=SecretStr("fictional"))
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "manage_database",
            "upgrade",
            "--from-revision",
            "0001_incidents",
            "--to-revision",
            "0002_logs",
            "--reviewed-sha256",
            "wrong" if failure == "hash" else digest,
        ],
    )
    engine = MagicMock()
    with (
        patch.object(manage_database, "database_engine", return_value=engine),
        patch.object(manage_database, "migration_sql", return_value=sql),
        patch.object(manage_database, "inspect_target", return_value=before),
        patch.object(manage_database, "verify_schema"),
        patch.object(
            manage_database,
            "protected_tables",
            return_value={"incidents": "changed" if failure == "protected_data" else "before"},
        ),
        patch.object(manage_database, "unrelated_fingerprint", return_value=("changed", 1)),
        patch.object(manage_database.command, "upgrade") as upgrade,
    ):
        with pytest.raises(SchemaSafetyStop):
            manage_database.main()
        if failure in {"hash", "baseline"}:
            upgrade.assert_not_called()
        else:
            upgrade.assert_called_once()
        assert engine.begin.return_value.__exit__.call_args.args[0] is SchemaSafetyStop
    engine.dispose.assert_called_once()
