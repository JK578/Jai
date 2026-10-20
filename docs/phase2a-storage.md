# Phase 2A: Persistent incident storage

Completed locally on native Windows, Python 3.15.0. This continues the earlier connection-only
Phase 2A verification and stops before Phase 2B authentication/access work.

## Implemented behavior

The existing POST/list/detail incident endpoints and their request/response fields are
unchanged. Auto storage selects PostgreSQL when DATABASE_URL is configured; explicit
memory mode stays available for offline tests/demos. PostgreSQL failure never silently
falls back to memory. IDs, enums, UTC timestamps and ordering remain domain-controlled.

The SQLAlchemy adapter uses the existing repository protocol. Each method owns a fresh
Session, closes it on all paths, commits successful writes, and rolls back failed writes
or completed reads. Immutable domain objects cross the infrastructure boundary. Engine
pool: two connections, no overflow, pre-ping, 300-second recycle, five-second connect timeout,
two-second pool wait, three-second SQL statement timeout. Prepared statements are disabled
for pooler compatibility. SSL is enforced; verify-ca/verify-full settings are preserved.

Secrets are hidden/excluded Pydantic SecretStr values and never serialized to the frontend.
Database exceptions become fixed 503/409 responses and sanitized log events. Readiness checks
the mapped incident table and connection; liveness does not query PostgreSQL. Readiness's
existing status/service fields remain, with an additive non-secret storage field used by
the frontend to label PostgreSQL vs temporary memory storage correctly.

## Schema and migration evidence

Revision `0001_incidents` creates:

| Object | Definition |
|---|---|
| incidentiq | Private application schema |
| incidentiq.incidents.id | UUID primary key, application-generated |
| title | VARCHAR(200), required, nonblank/bounded CHECK |
| description | TEXT, required, nonblank/10000-character CHECK |
| severity | VARCHAR(8), required; critical/high/medium/low CHECK |
| status | VARCHAR(13), required; open/investigating/resolved CHECK |
| service_name | VARCHAR(100), required, nonblank/bounded CHECK |
| created_at / updated_at | Required TIMESTAMPTZ; updated_at >= created_at CHECK |
| ix_incidents_created_id | B-tree on created_at/id, supports reverse newest-first scan |
| public.incidentiq_alembic_version | Dedicated Alembic revision tracking table |

Migration safety was executed, not assumed:

1. Read-only inspection found no conflicting app schema/table/tracking state. Recorded
   186 unrelated relations and a metadata fingerprint in [inspection.json](migrations/inspection.json).
2. Generated and reviewed [0001_incidents.sql](migrations/0001_incidents.sql). No DROP,
   reset, unrelated table ALTER, or existing-data DELETE appears. ALTER/REVOKE targets
   refer only to the newly created IncidentIQ objects.
3. Applied the exact reviewed SQL plan hash through the guarded Alembic command in a
   transaction with an advisory lock, bounded DDL timeouts and a fresh preflight check.
4. The unrelated metadata fingerprint was unchanged before commit. Post-application
   [applied.json](migrations/applied.json) confirms eight columns, six CHECK constraints,
   primary key, ordering index, RLS and revoked anon/authenticated Data API privileges.

The generated SQL SHA256 is
`a4059a1b83af6b5135a884a1b134846f45438d01cea14c3ad2433a14c90d64cf`.
There is no create_all(), migration on startup, reset or automatic schema adoption.
Unexpected initial schema differences stop the guard. Initial downgrade is disabled;
future revisions require another explicit reviewed plan. The applied revision is immutable.

## Executed checks

| Check | Actual result |
|---|---|
| Default backend suite | 45 passed; 2 live tests skipped by default; existing HTTPX deprecation warning |
| Opt-in PostgreSQL integration | 2 passed; writes enclosed in rolled-back outer transactions |
| Ruff lint/format, API/migrations/scripts | Passed |
| pip check | No broken requirements found |
| Frontend tests | 12 passed |
| Frontend lint and TypeScript | Passed |
| Production build | Passed; one worker; root and both incident proxy routes compiled |
| Memory HTTP smoke | All six scenario groups passed |
| PostgreSQL HTTP smoke | All six scenario groups passed, including persistence after actual process restart |
| Applied schema/security inspection | Passed; unrelated metadata unchanged |

Live integration tests cover actual repository roundtrips, ordering, duplicate rejection,
rollback recovery and API compatibility across application instances. The default suite
covers session cleanup, safe errors, SSL/pool configuration, readiness failure/recovery,
secret redaction, migration collision guards and unchanged incident/health contracts.
The first opt-in run failed during Windows temporary-directory setup, before database
tests ran; using a fresh workspace-local --basetemp and disabling pytest cache resolved it.
No failed migration or destructive cleanup was performed.

The real PostgreSQL smoke test started Next.js and FastAPI, created one incident through
the frontend proxy, listed/retrieved it, terminated the backend, started a new process,
and retrieved the exact same ID/content/timestamps. One development evidence incident is
intentionally retained. No pre-existing data was deleted. Other integration inserts rolled
back. Frontend DOM tests mock HTTP; the smoke tests exercise real loopback HTTP/cloud storage.

## Files created or modified

Created:

- `apps/api/src/incidentiq/infrastructure/{database,models,postgres}.py`
- `apps/api/alembic.ini`, `migrations/{env.py,script.py.mako,versions/0001_incidents.py}`
- `apps/api/tests/{conftest,test_postgres,test_database_integration}.py`
- `scripts/manage_database.py`
- `apps/web/tests/backend.test.ts`
- `docs/migrations/{0001_incidents.sql,inspection.json,applied.json}`
- `docs/adr/0006-postgres-persistence-and-reviewed-migrations.md` and this report

Modified:

- Backend `config.py`, `main.py`, `application/incidents.py`, `api/incidents.py`,
  `tests/{test_health,test_incidents}.py` (the latter import formatting only),
  `pyproject.toml`, `requirements-dev.lock.txt`, `.env.example`
- Frontend `src/lib/backend.ts`, `src/app/page.tsx`
- `scripts/smoke.py`, `.gitignore`, `README.md`
- `docs/{development,api,architecture,roadmap,verification,phase1b-completion,phase2a-verification}.md`

## Local startup

Keep DATABASE_URL only in ignored apps/api/api.env. Existing auto mode now uses PostgreSQL.
Fresh checkouts follow [development.md](development.md) for locked installation and the
initial migration workflow; this development database is already migrated.

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m uvicorn incidentiq.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/src
```

Second terminal:

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ\apps\web'
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
npm.cmd run dev
```

## Remaining limitations and Phase 2B recommendation

- The app is still unauthenticated and must remain local/loopback. The configured backend
  owner role bypasses RLS; user/tenant authorization and a least-privilege runtime role
  are Phase 2B work. Revoked Data API grants are not a substitute for API authorization.
- sslmode=require verifies encryption, not certificate/hostname identity. Establish the
  appropriate verify-full trust policy before deployment.
- No pagination, update/delete/status-transition routes, retry/idempotency keys, cloud
  tracing or production deployment were added. A timed-out POST may have succeeded;
  inspect the list before retrying. Use one worker for an 8 GB development machine.
- The migration guard intentionally handles the initial revision only; future revisions
  need another reviewed guard/plan. Remote GitHub Actions and real-browser visual/mobile
  QA were not executed. Existing ESLint 9 compatibility debt and Starlette warning remain.
- Python 3.15 and the existing frontend dependencies were preserved. Alembic 1.20.0 and
  its Windows dependencies installed successfully without native compilation/downgrades.

Phase 2A is complete locally. Recommend Phase 2B: authentication, tenant-scoped access,
restricted database privileges, authorization tests and production SSL trust configuration.
No Phase 2B, LLM, MCP, RAG or LangGraph implementation was performed. Await approval.
