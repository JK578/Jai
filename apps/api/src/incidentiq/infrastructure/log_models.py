"""Bounded log ingestion mappings; timestamps without a source zone stay naive."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from incidentiq.infrastructure.models import SCHEMA, Base


class DatasetRow(Base):
    __tablename__ = "log_datasets"
    __table_args__ = (UniqueConstraint("slug", name="uq_log_dataset_slug"), {"schema": SCHEMA})
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60))
    manifest_json: Mapped[str] = mapped_column(Text)


class FileRow(Base):
    __tablename__ = "log_files"
    __table_args__ = (
        UniqueConstraint("dataset_id", "sha256", name="uq_log_file_digest"),
        CheckConstraint(
            "byte_count > 0 AND byte_count <= 2097152 AND line_count BETWEEN 1 AND 2000",
            name="ck_log_file_bounds",
        ),
        {"schema": SCHEMA},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.log_datasets.id", ondelete="RESTRICT")
    )
    sha256: Mapped[str] = mapped_column(String(64))
    byte_count: Mapped[int] = mapped_column(Integer)
    line_count: Mapped[int] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(40))
    source_path: Mapped[str] = mapped_column(String(200))
    source_commit: Mapped[str] = mapped_column(String(40))


class RunRow(Base):
    __tablename__ = "log_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running','completed','partial','failed')", name="ck_log_run_state"
        ),
        CheckConstraint(
            "processed = inserted + duplicates + rejected AND processed = last_committed_line "
            "AND inserted >= 0 AND duplicates >= 0 AND rejected >= 0 AND processed <= 2000",
            name="ck_log_run_counts",
        ),
        CheckConstraint(
            "lease_expires_at > heartbeat_at AND heartbeat_at >= started_at",
            name="ck_log_run_lease",
        ),
        CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state <> 'running' AND finished_at IS NOT NULL)",
            name="ck_log_run_finish",
        ),
        Index(
            "uq_log_one_worker", "state", unique=True, postgresql_where=text("state = 'running'")
        ),
        Index("ix_log_runs_started", "started_at", "id"),
        {"schema": SCHEMA},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    file_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.log_files.id", ondelete="RESTRICT"))
    parser_version: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(12))
    processed: Mapped[int] = mapped_column(Integer)
    inserted: Mapped[int] = mapped_column(Integer)
    duplicates: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    last_committed_line: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    owner_token: Mapped[UUID] = mapped_column(Uuid)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(40))


class EventRow(Base):
    __tablename__ = "log_events"
    __table_args__ = (
        UniqueConstraint("file_id", "source_line", name="uq_log_event_line"),
        CheckConstraint("source_line BETWEEN 1 AND 2000", name="ck_log_event_line"),
        CheckConstraint(
            "octet_length(raw_line_sha256) = 32 AND octet_length(raw_line) <= 16384 "
            "AND octet_length(message) <= 16384",
            name="ck_log_event_size",
        ),
        CheckConstraint(
            "normalized_level IN ('emergency','alert','critical','error','warning',"
            "'notice','info','debug')",
            name="ck_log_event_level",
        ),
        CheckConstraint("event_time_utc IS NULL", name="ck_log_event_unknown_zone"),
        Index("ix_log_event_time", "file_id", "event_time_local", "source_line"),
        Index("ix_log_event_level", "file_id", "normalized_level", "source_line"),
        {"schema": SCHEMA},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    file_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.log_files.id", ondelete="RESTRICT"))
    source_line: Mapped[int] = mapped_column(Integer)
    source_time_text: Mapped[str] = mapped_column(String(40))
    event_time_local: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    event_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_level: Mapped[str] = mapped_column(String(16))
    normalized_level: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    raw_line: Mapped[str] = mapped_column(Text)
    raw_line_sha256: Mapped[bytes] = mapped_column(LargeBinary)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ErrorRow(Base):
    __tablename__ = "log_ingestion_errors"
    __table_args__ = (
        CheckConstraint(
            "source_line BETWEEN 1 AND 2000 AND sample_number BETWEEN 1 AND 100 "
            "AND octet_length(raw_line_sha256) = 32",
            name="ck_log_error_bounds",
        ),
        UniqueConstraint("run_id", "sample_number", name="uq_log_error_sample"),
        {"schema": SCHEMA},
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.log_ingestion_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    source_line: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_number: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str] = mapped_column(String(40))
    raw_line_sha256: Mapped[bytes] = mapped_column(LargeBinary)
