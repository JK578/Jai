"""Persistence mapping; domain objects remain independent of SQLAlchemy."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "incidentiq"


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_incidents_title"),
        CheckConstraint(
            "char_length(btrim(description)) BETWEEN 1 AND 10000", name="ck_incidents_description"
        ),
        CheckConstraint(
            "char_length(btrim(service_name)) BETWEEN 1 AND 100", name="ck_incidents_service"
        ),
        CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_incidents_severity"
        ),
        CheckConstraint(
            "status IN ('open','investigating','resolved')", name="ck_incidents_status"
        ),
        CheckConstraint("updated_at >= created_at", name="ck_incidents_timestamps"),
        Index("ix_incidents_created_id", "created_at", "id"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(13), nullable=False)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
