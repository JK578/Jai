"""Process-local storage. Lost on restart; use exactly one API worker."""

from threading import Lock
from uuid import UUID

from incidentiq.domain.incidents import Incident


class InMemoryIncidentRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Incident] = {}
        self._lock = Lock()

    def add(self, incident: Incident) -> None:
        with self._lock:
            if incident.id in self._items:
                raise ValueError("Incident ID already exists")
            self._items[incident.id] = incident

    def list(self) -> list[Incident]:
        with self._lock:
            return sorted(
                self._items.values(), key=lambda item: (item.created_at, item.id), reverse=True
            )

    def get(self, incident_id: UUID) -> Incident | None:
        with self._lock:
            return self._items.get(incident_id)
