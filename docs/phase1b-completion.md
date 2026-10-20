# Phase 1B completion

Implemented and verified on native Windows with Python 3.15.0 and Node 24.22.0.
Scope ends at incident domain foundation. No Phase 2 or AI/cloud integrations were added.

## Components and files

Created:

- `apps/api/src/incidentiq/domain/{__init__,incidents}.py`: immutable incident entity,
  severity/status enums, UUID and text/timestamp invariants.
- `apps/api/src/incidentiq/application/{__init__,incidents}.py`: repository protocol,
  IncidentService and not-found domain/application error.
- `apps/api/src/incidentiq/infrastructure/{__init__,memory}.py`: per-app lock-protected
  repository, snapshot lists, deterministic newest-first ordering.
- `apps/api/src/incidentiq/api/{__init__,incidents}.py`: versioned REST routes and
  Pydantic request/response contracts.
- `apps/api/tests/test_incidents.py`: domain, repository/service and HTTP integration tests.
- `apps/web/src/lib/{incidents,incident-proxy}.ts`: typed client validation/API handling
  and server-side upstream forwarding.
- `apps/web/src/components/{create-incident-form,incident-workspace}.tsx`: create form,
  list, selected details, loading/empty/error states and retries.
- `apps/web/src/app/api/v1/incidents/route.ts` and `[incident_id]/route.ts`: same-origin routes.
- `apps/web/tsconfig.test.json`, `tests/{setup.ts,fixtures.ts,incidents.test.ts,workspace.test.tsx}`:
  Node test-runner configuration and DOM/client/proxy tests.
- `docs/api.md`, `docs/adr/0005-incident-domain-and-ephemeral-storage.md`, this report.

Modified:

- `apps/api/src/incidentiq/main.py`: repository composition and incident router registration.
- `apps/web/src/app/page.tsx`: incident workspace and explicit temporary-storage notice.
- `apps/web/{package.json,package-lock.json,tsconfig.json,eslint.config.mjs}`: dev-only DOM
  testing dependencies, test script, output exclusions.
- `.gitignore`, `.github/workflows/ci.yml`, `scripts/smoke.py`: test output ignored,
  frontend tests in CI, expanded live HTTP smoke checks.
- `README.md`, `docs/{architecture,development,roadmap,phase1-review,verification}.md`:
  API/workflow/setup, architecture and milestone status updates; prior reports marked historical.

## API and decisions

POST `/api/v1/incidents` returns 201 with Location. GET collection returns an array;
GET `/{incident_id}` returns an incident, 404 for unknown UUID, or 422 for invalid UUID.
Strings are trimmed and bounded; extra fields are rejected. New incidents are open with
server-generated UUID4 IDs and equal UTC created/updated timestamps. No client-assigned
identity/status/timestamps are accepted. Health endpoints retain their original behavior.

Domain code imports only the standard library. The application depends on a repository
protocol, and the composition root selects the adapter. Pydantic lives at the HTTP boundary.
Next.js forwards fixed incident paths so the browser needs no CORS setup or backend URL.
The schema, contracts and adapter seam can be preserved when introducing persistent storage.

## Executed validation

| Check | Actual result |
|---|---|
| pytest apps/api/tests | 30 passed, one existing Starlette HTTPX deprecation warning |
| Ruff lint, API and smoke script | Passed |
| Ruff formatting, API and smoke script | Passed |
| pip check | No broken requirements found |
| npm test | 11 passed, zero failed |
| npm run lint | Passed |
| npm run typecheck | Passed |
| npm run build | Passed; one worker; root and both forwarding routes compiled |
| scripts/smoke.py | Six scenario groups passed: ready; real proxy incident workflow/validation; not ready; restart clears data; stopped API UI; stopped API proxy 502 |

Tests exercise whitespace/length/enum validation, generated identity/timestamps, immutable
domain rules, repository isolation/snapshots, lookup failures, schema errors, health regressions,
duplicate-submit protection, input retention, list loading/empty/error recovery, creation,
detail selection/retry, malformed responses and sanitized proxy failures. Frontend DOM tests
mock HTTP; the smoke test separately exercises actual Next.js/FastAPI loopback HTTP.

## Startup

Terminal 1:

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m uvicorn incidentiq.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/src
```

Terminal 2:

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ\apps\web'
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
$env:NEXT_TELEMETRY_DISABLED = '1'
npm.cmd run dev
```

Open http://127.0.0.1:3000. Fresh checkouts use the installation steps in development.md.

## Limitations and Phase 2 readiness

- Data is process-local, unbounded and temporary. Restart/reload destroys it. One API worker only.
- No persistence, authentication, tenancy, pagination, editing, deletion or status-transition API.
- A timed-out POST may have succeeded upstream; inspect/refresh the list before retrying.
  There is no idempotency-key mechanism in this phase.
- Frontend tests use jsdom, not real-browser/mobile/accessibility certification.
- Starlette's HTTPX test-client warning and the ESLint 9/plugin compatibility debt remain.
  No Python downgrade, native compilation or Python dependency replacement was needed.
- GitHub Actions was updated but has not run remotely. No commit or publication was requested.
- SQLAlchemy/PostgreSQL-driver/migration compatibility is not validated by this milestone.
  Verify that exact dependency combination on Windows Python 3.15 when Phase 2 is approved.

Phase 1B acceptance is complete locally. Ready for Phase 2 planning and a reviewed initial
CI baseline; persistent storage and access enforcement remain work for the next approved
milestone. Stop here and await approval before implementing Phase 2.
