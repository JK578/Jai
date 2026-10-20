"""Incident identity and creation invariants; no infrastructure dependencies."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

TITLE_MAX = 200
DESCRIPTION_MAX = 10_000
SERVICE_MAX = 100


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class Incident:
    id: UUID
    title: str
    description: str
    severity: Severity
    status: IncidentStatus
    service_name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ValueError("Incident ID must be a UUID")
        for name, limit in (
            ("title", TITLE_MAX),
            ("description", DESCRIPTION_MAX),
            ("service_name", SERVICE_MAX),
        ):
            value = getattr(self, name).strip()
            if not 1 <= len(value) <= limit:
                raise ValueError(f"{name} must contain 1 to {limit} characters")
            object.__setattr__(self, name, value)
        if not isinstance(self.severity, Severity) or not isinstance(self.status, IncidentStatus):
            raise ValueError("Invalid severity or status")
        if self.created_at.utcoffset() is None or self.updated_at.utcoffset() is None:
            raise ValueError("Incident timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")

    @classmethod
    def create(
        cls, title: str, description: str, severity: Severity, service_name: str
    ) -> Incident:
        now = datetime.now(UTC)
        return cls(
            uuid4(), title, description, severity, IncidentStatus.OPEN, service_name, now, now
        )
