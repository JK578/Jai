-- Separate prerequisite, NOT applied by Alembic or application startup.
-- Review and authorize independently; changes extension-owned types/functions.
-- Expected preflight: vector available but not installed; schema extensions exists.
-- Do not relocate, upgrade or drop an existing extension.
BEGIN;
SET LOCAL statement_timeout = '15000ms';
SET LOCAL lock_timeout = '5000ms';
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN
        RAISE EXCEPTION 'Vector already installed; inspect before proceeding';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='extensions') THEN
        RAISE EXCEPTION 'Expected extensions schema missing';
    END IF;
END $$;
CREATE EXTENSION vector WITH SCHEMA extensions VERSION '0.8.2';
COMMIT;
