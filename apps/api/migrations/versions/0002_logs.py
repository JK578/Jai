"""Add isolated log ingestion tables. Frozen DDL; no dependency on evolving ORM models."""

from alembic import op

revision = "0002_logs"
down_revision = "0001_incidents"
branch_labels = None
depends_on = None

STATEMENTS = (
    """CREATE TABLE incidentiq.log_datasets (
    id UUID NOT NULL,
    slug VARCHAR(60) NOT NULL,
    manifest_json TEXT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_log_dataset_slug UNIQUE (slug)
)""",
    """ALTER TABLE incidentiq.log_datasets ENABLE ROW LEVEL SECURITY""",
    """REVOKE ALL ON TABLE incidentiq.log_datasets FROM PUBLIC, anon, authenticated""",
    """CREATE TABLE incidentiq.log_files (
    id UUID NOT NULL,
    dataset_id UUID NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    byte_count INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    parser_version VARCHAR(40) NOT NULL,
    source_path VARCHAR(200) NOT NULL,
    source_commit VARCHAR(40) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_log_file_digest UNIQUE (dataset_id, sha256),
    CONSTRAINT ck_log_file_bounds CHECK (byte_count > 0 AND byte_count <= 2097152 AND line_count
        BETWEEN 1 AND 2000),
    FOREIGN KEY(dataset_id) REFERENCES incidentiq.log_datasets (id) ON DELETE RESTRICT
)""",
    """ALTER TABLE incidentiq.log_files ENABLE ROW LEVEL SECURITY""",
    """REVOKE ALL ON TABLE incidentiq.log_files FROM PUBLIC, anon, authenticated""",
    """CREATE TABLE incidentiq.log_events (
    id UUID NOT NULL,
    file_id UUID NOT NULL,
    source_line INTEGER NOT NULL,
    source_time_text VARCHAR(40) NOT NULL,
    event_time_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    event_time_utc TIMESTAMP WITH TIME ZONE,
    original_level VARCHAR(16) NOT NULL,
    normalized_level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    raw_line TEXT NOT NULL,
    raw_line_sha256 BYTEA NOT NULL,
    ingested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_log_event_line UNIQUE (file_id, source_line),
    CONSTRAINT ck_log_event_line CHECK (source_line BETWEEN 1 AND 2000),
    CONSTRAINT ck_log_event_size CHECK (octet_length(raw_line_sha256) = 32 AND
        octet_length(raw_line) <= 16384 AND octet_length(message) <= 16384),
    CONSTRAINT ck_log_event_level CHECK (normalized_level IN
        ('emergency','alert','critical','error','warning','notice','info','debug')),
    CONSTRAINT ck_log_event_unknown_zone CHECK (event_time_utc IS NULL),
    FOREIGN KEY(file_id) REFERENCES incidentiq.log_files (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_log_event_level ON incidentiq.log_events (file_id, normalized_level,
        source_line)""",
    """CREATE INDEX ix_log_event_time ON incidentiq.log_events (file_id, event_time_local,
        source_line)""",
    """ALTER TABLE incidentiq.log_events ENABLE ROW LEVEL SECURITY""",
    """REVOKE ALL ON TABLE incidentiq.log_events FROM PUBLIC, anon, authenticated""",
    """CREATE TABLE incidentiq.log_ingestion_runs (
    id UUID NOT NULL,
    file_id UUID NOT NULL,
    parser_version VARCHAR(40) NOT NULL,
    state VARCHAR(12) NOT NULL,
    processed INTEGER NOT NULL,
    inserted INTEGER NOT NULL,
    duplicates INTEGER NOT NULL,
    rejected INTEGER NOT NULL,
    last_committed_line INTEGER NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL,
    lease_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    owner_token UUID NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    failure_code VARCHAR(40),
    PRIMARY KEY (id),
    CONSTRAINT ck_log_run_state CHECK (state IN ('running','completed','partial','failed')),
    CONSTRAINT ck_log_run_counts CHECK (processed = inserted + duplicates + rejected AND
        processed = last_committed_line AND inserted >= 0 AND duplicates >= 0 AND rejected >= 0
        AND processed <= 2000),
    CONSTRAINT ck_log_run_lease CHECK (lease_expires_at > heartbeat_at AND heartbeat_at >=
        started_at),
    CONSTRAINT ck_log_run_finish CHECK ((state = 'running' AND finished_at IS NULL) OR (state <>
        'running' AND finished_at IS NOT NULL)),
    FOREIGN KEY(file_id) REFERENCES incidentiq.log_files (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_log_runs_started ON incidentiq.log_ingestion_runs (started_at, id)""",
    """CREATE UNIQUE INDEX uq_log_one_worker ON incidentiq.log_ingestion_runs (state) WHERE
        state = 'running'""",
    """ALTER TABLE incidentiq.log_ingestion_runs ENABLE ROW LEVEL SECURITY""",
    """REVOKE ALL ON TABLE incidentiq.log_ingestion_runs FROM PUBLIC, anon, authenticated""",
    """CREATE TABLE incidentiq.log_ingestion_errors (
    run_id UUID NOT NULL,
    source_line INTEGER NOT NULL,
    sample_number INTEGER NOT NULL,
    error_code VARCHAR(40) NOT NULL,
    raw_line_sha256 BYTEA NOT NULL,
    PRIMARY KEY (run_id, source_line),
    CONSTRAINT ck_log_error_bounds CHECK (source_line BETWEEN 1 AND 2000 AND sample_number
        BETWEEN 1 AND 100 AND octet_length(raw_line_sha256) = 32),
    CONSTRAINT uq_log_error_sample UNIQUE (run_id, sample_number),
    FOREIGN KEY(run_id) REFERENCES incidentiq.log_ingestion_runs (id) ON DELETE RESTRICT
)""",
    """ALTER TABLE incidentiq.log_ingestion_errors ENABLE ROW LEVEL SECURITY""",
    """REVOKE ALL ON TABLE incidentiq.log_ingestion_errors FROM PUBLIC, anon, authenticated""",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Explicit downgrade only; removes this revision's data. Never run automatically.
    op.drop_table("log_ingestion_errors", schema="incidentiq")
    op.drop_table("log_ingestion_runs", schema="incidentiq")
    op.drop_table("log_events", schema="incidentiq")
    op.drop_table("log_files", schema="incidentiq")
    op.drop_table("log_datasets", schema="incidentiq")
