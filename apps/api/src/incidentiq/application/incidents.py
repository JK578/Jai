from typing import Protocol
from uuid import UUID

from incidentiq.domain.incidents import Incident, Severity


class IncidentRepository(Protocol):
    def add(self, incident: Incident) -> None: ...
    def list(self) -> list[Incident]: ...
    def get(self, incident_id: UUID) -> Incident | None: ...


class IncidentNotFound(Exception):
    """The requested incident does not exist."""


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self._repository = repository

    def create(
        self, title: str, description: str, severity: Severity, service_name: str
    ) -> Incident:
        incident = Incident.create(title, description, severity, service_name)
        self._repository.add(incident)
        return incident

    def list(self) -> list[Incident]:
        return self._repository.list()

    def get(self, incident_id: UUID) -> Incident:
        incident = self._repository.get(incident_id)
        if incident is None:
            raise IncidentNotFound(incident_id)
        return incident
