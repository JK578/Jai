"""Add resource ownership and restricted-runtime RLS policies; preserve source rows."""

from alembic import op

revision = "0004_access"
down_revision = "0003_retrieval"
branch_labels = None
depends_on = None

TENANT = "nullif(current_setting('incidentiq.tenant_id', true), '')::uuid"
FILE_SCOPE = (
    "EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' "
    f"AND o.resource_id=file_id AND o.tenant_id={TENANT})"
)
INCIDENT_SCOPE = (
    "EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='incident' "
    f"AND o.resource_id=id AND o.tenant_id={TENANT})"
)

STATEMENTS = (
    "CREATE ROLE incidentiq_runtime NOLOGIN NOSUPERUSER NOCREATEDB "
    "NOCREATEROLE NOREPLICATION NOBYPASSRLS",
    """CREATE TABLE incidentiq.resource_owners (
        kind VARCHAR(10) NOT NULL,
        resource_id UUID NOT NULL,
        tenant_id UUID NOT NULL,
        PRIMARY KEY (kind, resource_id),
        CONSTRAINT ck_resource_kind CHECK (kind IN ('incident','file'))
    )""",
    "CREATE INDEX ix_resource_tenant ON incidentiq.resource_owners (tenant_id, kind)",
    "ALTER TABLE incidentiq.resource_owners ENABLE ROW LEVEL SECURITY",
    "REVOKE ALL ON TABLE incidentiq.resource_owners FROM PUBLIC, anon, authenticated",
    "GRANT USAGE ON SCHEMA incidentiq, extensions TO incidentiq_runtime",
    "GRANT SELECT ON incidentiq.incidents, incidentiq.log_datasets, incidentiq.log_files, "
    "incidentiq.log_events, incidentiq.log_ingestion_runs, incidentiq.log_ingestion_errors, "
    "incidentiq.retrieval_documents, incidentiq.resource_owners TO incidentiq_runtime",
    "GRANT INSERT ON incidentiq.incidents, incidentiq.resource_owners TO incidentiq_runtime",
    "CREATE POLICY resource_select ON incidentiq.resource_owners FOR SELECT "
    f"TO incidentiq_runtime USING (tenant_id={TENANT})",
    "CREATE POLICY resource_insert ON incidentiq.resource_owners FOR INSERT "
    f"TO incidentiq_runtime WITH CHECK (kind='incident' AND tenant_id={TENANT})",
    "CREATE POLICY incident_select ON incidentiq.incidents FOR SELECT "
    f"TO incidentiq_runtime USING ({INCIDENT_SCOPE})",
    "CREATE POLICY incident_insert ON incidentiq.incidents FOR INSERT "
    f"TO incidentiq_runtime WITH CHECK ({INCIDENT_SCOPE})",
    "CREATE POLICY file_select ON incidentiq.log_files FOR SELECT TO incidentiq_runtime "
    "USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' "
    f"AND o.resource_id=id AND o.tenant_id={TENANT}))",
    "CREATE POLICY event_select ON incidentiq.log_events FOR SELECT "
    f"TO incidentiq_runtime USING ({FILE_SCOPE})",
    "CREATE POLICY run_select ON incidentiq.log_ingestion_runs FOR SELECT "
    f"TO incidentiq_runtime USING ({FILE_SCOPE})",
    "CREATE POLICY retrieval_select ON incidentiq.retrieval_documents FOR SELECT "
    f"TO incidentiq_runtime USING ({FILE_SCOPE})",
    "CREATE POLICY dataset_select ON incidentiq.log_datasets FOR SELECT TO incidentiq_runtime "
    "USING (EXISTS (SELECT 1 FROM incidentiq.log_files f WHERE f.dataset_id=log_datasets.id))",
    "CREATE POLICY error_select ON incidentiq.log_ingestion_errors FOR SELECT "
    "TO incidentiq_runtime "
    "USING (EXISTS (SELECT 1 FROM incidentiq.log_ingestion_runs r WHERE r.id=run_id))",
)


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Security rollback requires a separately reviewed policy change")
