BEGIN;

-- Running upgrade 0002_logs -> 0003_retrieval

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
        WHERE e.extname='vector' AND n.nspname='extensions') THEN
        RAISE EXCEPTION 'Enable reviewed vector extension in extensions schema first';
    END IF;
END $$;

CREATE TABLE incidentiq.retrieval_documents (
    event_id UUID NOT NULL,
    file_id UUID NOT NULL,
    model VARCHAR(80) NOT NULL,
    dimensions INTEGER NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    embedding extensions.vector(512) NOT NULL,
    indexed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (event_id),
    CONSTRAINT ck_retrieval_model CHECK (length(model) BETWEEN 1 AND 80 AND dimensions=512),
    CONSTRAINT ck_retrieval_content CHECK (octet_length(content) BETWEEN 1 AND 8000
        AND content_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT ck_retrieval_vector CHECK (extensions.vector_norm(embedding) > 0),
    FOREIGN KEY(event_id) REFERENCES incidentiq.log_events (id) ON DELETE RESTRICT,
    FOREIGN KEY(file_id) REFERENCES incidentiq.log_files (id) ON DELETE RESTRICT
);

CREATE INDEX ix_retrieval_file ON incidentiq.retrieval_documents (file_id);

ALTER TABLE incidentiq.retrieval_documents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE incidentiq.retrieval_documents FROM PUBLIC, anon, authenticated;

UPDATE public.incidentiq_alembic_version SET version_num='0003_retrieval' WHERE public.incidentiq_alembic_version.version_num = '0002_logs';

COMMIT;

