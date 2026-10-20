BEGIN;

CREATE TABLE public.incidentiq_alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT incidentiq_alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_incidents

CREATE SCHEMA incidentiq;

CREATE TABLE incidentiq.incidents (
    id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    severity VARCHAR(8) NOT NULL, 
    status VARCHAR(13) NOT NULL, 
    service_name VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_incidents_title CHECK (char_length(btrim(title)) BETWEEN 1 AND 200), 
    CONSTRAINT ck_incidents_description CHECK (char_length(btrim(description)) BETWEEN 1 AND 10000), 
    CONSTRAINT ck_incidents_service CHECK (char_length(btrim(service_name)) BETWEEN 1 AND 100), 
    CONSTRAINT ck_incidents_severity CHECK (severity IN ('critical','high','medium','low')), 
    CONSTRAINT ck_incidents_status CHECK (status IN ('open','investigating','resolved')), 
    CONSTRAINT ck_incidents_timestamps CHECK (updated_at >= created_at)
);

CREATE INDEX ix_incidents_created_id ON incidentiq.incidents (created_at, id);

ALTER TABLE incidentiq.incidents ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON SCHEMA incidentiq FROM PUBLIC, anon, authenticated;

REVOKE ALL ON TABLE incidentiq.incidents FROM PUBLIC, anon, authenticated;

ALTER TABLE public.incidentiq_alembic_version ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.incidentiq_alembic_version FROM PUBLIC, anon, authenticated;

INSERT INTO public.incidentiq_alembic_version (version_num) VALUES ('0001_incidents') RETURNING public.incidentiq_alembic_version.version_num;

COMMIT;

