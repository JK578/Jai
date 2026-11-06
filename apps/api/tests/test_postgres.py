from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from incidentiq.application.incidents import IncidentConflict, IncidentStorageUnavailable
from incidentiq.config import Settings
from incidentiq.domain.incidents import Incident, Severity
from incidentiq.infrastructure.database import Database, database_engine
from incidentiq.infrastructure.models import IncidentRow
from incidentiq.infrastructure.postgres import PostgresIncidentRepository, to_domain
from incidentiq.main import create_app
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from scripts.manage_database import PLAN, migration_sql, pristine


def row_for(incident: Incident) -> IncidentRow:
    return IncidentRow(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        severity=incident.severity.value,
        status=incident.status.value,
        service_name=incident.service_name,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def test_domain_mapping_and_repository_session_lifecycle() -> None:
    incident = Incident.create("Unit incident", "Description", Severity.HIGH, "unit-api")
    row = row_for(incident)
    assert to_domain(row) == incident
    factory = MagicMock()
    session = factory.begin.return_value.__enter__.return_value
    repository = PostgresIncidentRepository(factory)
    repository.add(incident)
    assert to_domain(session.add.call_args.args[0]) == incident
    factory.begin.return_value.__exit__.assert_called_once_with(None, None, None)
    reader = factory.return_value.__enter__.return_value
    reader.scalars.return_value = [row]
    assert repository.list() == [incident]
    reader.get.return_value = row
    assert repository.get(incident.id) == incident
    reader.get.return_value = None
    assert repository.get(incident.id) is None
    assert factory.return_value.__exit__.call_count == 3


@pytest.mark.parametrize("operation", ["add", "list", "get"])
def test_database_errors_are_sanitized(operation: str) -> None:
    factory = MagicMock()
    secret_message = "internal SQL and fake credential must not appear"
    factory.begin.return_value.__enter__.side_effect = SQLAlchemyError(secret_message)
    factory.return_value.__enter__.side_effect = SQLAlchemyError(secret_message)
    repository = PostgresIncidentRepository(factory)
    incident = Incident.create("Unit", "Description", Severity.LOW, "api")
    arguments = [] if operation == "list" else [incident if operation == "add" else incident.id]
    with pytest.raises(IncidentStorageUnavailable) as caught:
        getattr(repository, operation)(*arguments)
    assert secret_message not in str(caught.value)
    assert caught.value.__suppress_context__


def test_integrity_error_has_safe_conflict_response() -> None:
    factory = MagicMock()
    factory.begin.return_value.__exit__.side_effect = IntegrityError("private", {}, Exception())
    with pytest.raises(IncidentConflict, match="Incident could not be stored"):
        PostgresIncidentRepository(factory).add(
            Incident.create("Unit", "Description", Severity.LOW, "api"),
        )


def test_engine_settings_enforce_ssl_and_small_pool() -> None:
    with patch("incidentiq.infrastructure.database.create_engine") as create:
        database_engine(SecretStr("postgresql://unit:unit@localhost/postgres?sslmode=disable"))
        options = create.call_args.kwargs
        assert options["connect_args"]["sslmode"] == "require"
        assert options["connect_args"]["connect_timeout"] == 5
        assert options["connect_args"]["prepare_threshold"] is None
        assert options["pool_size"] == 2 and options["max_overflow"] == 0
        assert options["pool_pre_ping"] is True and options["hide_parameters"] is True
    with pytest.raises(ValueError, match="details suppressed"):
        database_engine(SecretStr("not-a-url"))


def test_storage_exception_is_safe_over_http() -> None:
    repository = MagicMock()
    repository.list.side_effect = IncidentStorageUnavailable("private driver details")
    with TestClient(create_app(Settings(environment="test"), repository)) as client:
        response = client.get("/api/v1/incidents")
        assert response.status_code == 503
        assert response.json() == {"detail": "Incident storage unavailable"}


def test_database_readiness_and_shutdown_cleanup() -> None:
    with patch("incidentiq.main.Database") as factory:
        database = factory.return_value
        database.ready.return_value = False
        settings = Settings(environment="test", storage="postgres", database_url=SecretStr("test"))
        with TestClient(create_app(settings)) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 503
            database.ready.return_value = True
            assert client.get("/health/ready").status_code == 200
        database.close.assert_called_once()


def test_readiness_failure_closes_session() -> None:
    with patch("incidentiq.infrastructure.database.database_engine"):
        database = Database(SecretStr("test"))
    sessions = MagicMock()
    database.sessions = sessions
    sessions.return_value.__enter__.return_value.execute.side_effect = SQLAlchemyError("private")
    assert database.ready() is False
    sessions.return_value.__exit__.assert_called_once()


def test_offline_migration_only_targets_owned_objects() -> None:
    sql = migration_sql("base", "0001_incidents")
    assert PLAN.read_text(encoding="utf-8") == sql
    assert "CREATE SCHEMA incidentiq" in sql
    assert "CREATE TABLE incidentiq.incidents" in sql
    assert "CREATE TABLE public.incidentiq_alembic_version" in sql
    assert "DROP " not in sql.upper()
    for statement in sql.split(";"):
        if "ALTER TABLE" in statement:
            assert (
                "incidentiq.incidents" in statement
                or "public.incidentiq_alembic_version" in statement
            )


@pytest.mark.parametrize("collision", ["schema", "tracking", "public_incidents"])
def test_initial_migration_stops_on_unexpected_objects(collision: str) -> None:
    inspector = MagicMock()
    inspector.get_schema_names.return_value = (
        ["public", "incidentiq"] if collision == "schema" else ["public"]
    )
    inspector.has_table.side_effect = lambda table, schema: (
        table == "incidentiq_alembic_version"
        if collision == "tracking"
        else table == "incidents"
        if collision == "public_incidents"
        else False
    )
    with patch("scripts.migration_catalog.inspect", return_value=inspector):
        with pytest.raises(RuntimeError):
            pristine(MagicMock())


def test_database_configuration_excludes_credentials_from_repr_and_serialization() -> None:
    secret = "fictional-test-secret"
    settings = Settings(database_url=SecretStr(secret))
    assert secret not in repr(settings)
    assert "database_url" not in settings.model_dump()
    assert settings.persistent is True
