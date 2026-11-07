BEGIN;

-- Running upgrade 0003_retrieval -> 0004_access

CREATE ROLE incidentiq_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE TABLE incidentiq.resource_owners (
        kind VARCHAR(10) NOT NULL,
        resource_id UUID NOT NULL,
        tenant_id UUID NOT NULL,
        PRIMARY KEY (kind, resource_id),
        CONSTRAINT ck_resource_kind CHECK (kind IN ('incident','file'))
    );

CREATE INDEX ix_resource_tenant ON incidentiq.resource_owners (tenant_id, kind);

ALTER TABLE incidentiq.resource_owners ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE incidentiq.resource_owners FROM PUBLIC, anon, authenticated;

GRANT USAGE ON SCHEMA incidentiq, extensions TO incidentiq_runtime;

GRANT SELECT ON incidentiq.incidents, incidentiq.log_datasets, incidentiq.log_files, incidentiq.log_events, incidentiq.log_ingestion_runs, incidentiq.log_ingestion_errors, incidentiq.retrieval_documents, incidentiq.resource_owners TO incidentiq_runtime;

GRANT INSERT ON incidentiq.incidents, incidentiq.resource_owners TO incidentiq_runtime;

CREATE POLICY resource_select ON incidentiq.resource_owners FOR SELECT TO incidentiq_runtime USING (tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid);

CREATE POLICY resource_insert ON incidentiq.resource_owners FOR INSERT TO incidentiq_runtime WITH CHECK (kind='incident' AND tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid);

CREATE POLICY incident_select ON incidentiq.incidents FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='incident' AND o.resource_id=id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY incident_insert ON incidentiq.incidents FOR INSERT TO incidentiq_runtime WITH CHECK (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='incident' AND o.resource_id=id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY file_select ON incidentiq.log_files FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' AND o.resource_id=id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY event_select ON incidentiq.log_events FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' AND o.resource_id=file_id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY run_select ON incidentiq.log_ingestion_runs FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' AND o.resource_id=file_id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY retrieval_select ON incidentiq.retrieval_documents FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.resource_owners o WHERE o.kind='file' AND o.resource_id=file_id AND o.tenant_id=nullif(current_setting('incidentiq.tenant_id', true), '')::uuid));

CREATE POLICY dataset_select ON incidentiq.log_datasets FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.log_files f WHERE f.dataset_id=log_datasets.id));

CREATE POLICY error_select ON incidentiq.log_ingestion_errors FOR SELECT TO incidentiq_runtime USING (EXISTS (SELECT 1 FROM incidentiq.log_ingestion_runs r WHERE r.id=run_id));

UPDATE public.incidentiq_alembic_version SET version_num='0004_access' WHERE public.incidentiq_alembic_version.version_num = '0003_retrieval';

COMMIT;

