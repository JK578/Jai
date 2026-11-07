"""Authenticated HTTP composition; operator CLIs retain their separate owner connection."""

from threading import Lock

from incidentiq.application.access import principal
from incidentiq.application.incidents import IncidentService
from incidentiq.infrastructure.access import ScopedSessions
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.memory import InMemoryIncidentRepository
from incidentiq.infrastructure.postgres import PostgresIncidentRepository


class ScopedIncidentService:
    def __init__(self, database):
        self.database = database
        self.memory = {}
        self.lock = Lock()

    def service(self):
        actor = principal()
        if self.database:
            repo = PostgresIncidentRepository(
                ScopedSessions(self.database.sessions, actor), actor.tenant_id
            )
        else:
            with self.lock:
                repo = self.memory.setdefault(actor.tenant_id, InMemoryIncidentRepository())
        return IncidentService(repo)

    def create(self, *args):
        return self.service().create(*args)

    def list(self):
        return self.service().list()

    def get(self, identity):
        return self.service().get(identity)


class ScopedLogReader:
    def __init__(self, database):
        self.database = database

    def read(self, resource, **kwargs):
        sessions = ScopedSessions(self.database.sessions, principal())
        return PostgresLogRepository(sessions).read(resource, **kwargs)
