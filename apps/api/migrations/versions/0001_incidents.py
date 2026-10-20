"""Create only IncidentIQ-owned objects. No unrelated Supabase objects are altered."""

import sqlalchemy as sa
from alembic import op

revision = "0001_incidents"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA incidentiq")
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("status", sa.String(13), nullable=False),
        sa.Column("service_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 200", name="ck_incidents_title"
        ),
        sa.CheckConstraint(
            "char_length(btrim(description)) BETWEEN 1 AND 10000", name="ck_incidents_description"
        ),
        sa.CheckConstraint(
            "char_length(btrim(service_name)) BETWEEN 1 AND 100", name="ck_incidents_service"
        ),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_incidents_severity"
        ),
        sa.CheckConstraint(
            "status IN ('open','investigating','resolved')", name="ck_incidents_status"
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_incidents_timestamps"),
        schema="incidentiq",
    )
    op.create_index(
        "ix_incidents_created_id", "incidents", ["created_at", "id"], schema="incidentiq"
    )
    op.execute("ALTER TABLE incidentiq.incidents ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON SCHEMA incidentiq FROM PUBLIC, anon, authenticated")
    op.execute("REVOKE ALL ON TABLE incidentiq.incidents FROM PUBLIC, anon, authenticated")
    # Alembic creates this namespaced tracking table before running this revision.
    op.execute("ALTER TABLE public.incidentiq_alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute(
        "REVOKE ALL ON TABLE public.incidentiq_alembic_version FROM PUBLIC, anon, authenticated"
    )


def downgrade() -> None:
    raise RuntimeError("Destructive initial downgrade disabled; use a reviewed forward migration")
