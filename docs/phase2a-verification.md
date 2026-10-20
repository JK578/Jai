# Phase 2A database connection verification

Historical connection-only verification. The subsequently authorized
[persistent storage milestone](phase2a-storage.md) adds and verifies the reviewed schema.

Date: 2026-10-20. Native Windows, CPython 3.15.0.

| Check | Status | Result |
|---|---|---|
| Existing configuration inspection | PASS | Per user instruction, load_settings and probe now share apps/api/api.env with process-environment precedence; Settings itself has no database field |
| DATABASE_URL loading | PASS | Saved api.env loads successfully; connection fields validated without displaying values |
| SQLAlchemy and psycopg installation | PASS | SQLAlchemy 2.1.5, psycopg/psycopg-binary 3.3.6 installed from Windows CPython 3.15 wheels; imports succeeded |
| Supabase SELECT 1 | PASS | Latest read-only probe connected successfully and SELECT 1 returned 1; transaction rolled back and connection closed |
| SSL connectivity | PASS | psycopg client SSL flag confirmed encryption with sslmode=require; certificate/hostname identity verification was not tested |
| Python 3.15 local compatibility | PASS | Live SQLAlchemy/psycopg connection and query succeeded on Python 3.15.0; prior pip check and 31 backend tests passed with existing HTTPX deprecation warning |
| Secret handling | PASS | No credentials/URL or raw connection exceptions printed; Git confirms api.env ignored and untracked; credential file unchanged |
| No models, migrations or table changes | PASS | No database model/migration/table operations added or executed |

Added a standalone safe probe at scripts/verify_database.py and an optional database extra
in apps/api/pyproject.toml. Updated the existing dependency lock, commented environment
example, and development instructions. No database connection is added to API startup;
incidents still use the Phase 1B in-memory adapter.

The probe normalizes standard PostgreSQL URLs to SQLAlchemy's psycopg dialect, enforces
encrypted SSL policy (preserving verify-ca/verify-full when configured), uses NullPool,
disables prepared statements for pooler compatibility, runs SELECT 1 in a read-only
transaction, inspects psycopg's client SSL flag, then rolls back and closes. It suppresses
raw exceptions and prints fixed error categories only. The latest live connection and
query succeeded. SSL require confirms encryption, not certificate/hostname identity;
verify-full needs the appropriate certificate/trust configuration.

Earlier attempts were blocked by an empty .env, then DNS/URL configuration errors after
switching to api.env. Those blockers are resolved for the latest saved configuration.
The latest probe exited 0 with successful loading, SELECT 1, SSL and Python 3.15 driver
execution checks. No credential file was changed by the probe; no table changes or
migrations were performed. Phase 2A connection verification is complete.

Save updated connection details only in ignored apps/api/api.env, then rerun:

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe scripts/verify_database.py
```

Do not paste the URL into chat or command arguments. Stop at verification; do not implement
database models or run migrations until separately authorized.
