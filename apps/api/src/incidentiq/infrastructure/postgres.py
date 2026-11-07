from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from incidentiq.application.incidents import IncidentConflict, IncidentStorageUnavailable
from incidentiq.domain.incidents import Incident, IncidentStatus, Severity
from incidentiq.infrastructure.database import Database
from incidentiq.infrastructure.models import IncidentRow


def to_domain(row: IncidentRow) -> Incident:
    return Incident(
        row.id,
        row.title,
        row.description,
        Severity(row.severity),
        IncidentStatus(row.status),
        row.service_name,
        row.created_at,
        row.updated_at,
    )


class PostgresIncidentRepository:
    def __init__(self, sessions: sessionmaker[Session], tenant_id: UUID | None = None) -> None:
        self._sessions = sessions
        self._tenant_id = tenant_id

    def add(self, incident: Incident) -> None:
        try:
            with self._sessions.begin() as session:
                Database.bound_statement(session)
                if self._tenant_id is not None:
                    session.execute(
                        text("""INSERT INTO incidentiq.resource_owners
                        (kind, resource_id, tenant_id) VALUES ('incident', :id, :tenant)"""),
                        {"id": incident.id, "tenant": self._tenant_id},
                    )
                session.add(
                    IncidentRow(
                        id=incident.id,
                        title=incident.title,
                        description=incident.description,
                        severity=incident.severity.value,
                        status=incident.status.value,
                        service_name=incident.service_name,
                        created_at=incident.created_at,
                        updated_at=incident.updated_at,
                    )
                )
        except IntegrityError:
            raise IncidentConflict("Incident could not be stored") from None
        except SQLAlchemyError:
            raise IncidentStorageUnavailable("Incident storage unavailable") from None

    def list(self) -> list[Incident]:
        try:
            with self._sessions() as session:
                Database.bound_statement(session)
                rows = session.scalars(
                    select(IncidentRow)
                    .order_by(
                        IncidentRow.created_at.desc(),
                        IncidentRow.id.desc(),
                    )
                    .limit(100)
                )
                return [to_domain(row) for row in rows]
        except SQLAlchemyError, ValueError:
            raise IncidentStorageUnavailable("Incident storage unavailable") from None

    def get(self, incident_id: UUID) -> Incident | None:
        try:
            with self._sessions() as session:
                Database.bound_statement(session)
                row = session.get(IncidentRow, incident_id)
                return to_domain(row) if row is not None else None
        except SQLAlchemyError, ValueError:
            raise IncidentStorageUnavailable("Incident storage unavailable") from None
