# Native Windows developer setup

For the current authenticated workspace and MCP setup, start with
[the local completion/runbook](local-completion.md). Older milestone commands below are historical.

## Persistent storage and reviewed migrations

When DATABASE_URL is saved in ignored `apps/api/api.env`, default auto mode uses PostgreSQL.
Set INCIDENTIQ_STORAGE=memory for an offline demo or postgres to require persistence and
fail configuration validation when the URL is missing. No silent fallback occurs after
selecting PostgreSQL. Keep URLs out of shell arguments and NEXT_PUBLIC variables.

The configured development database now has revision 0004_access applied. Do not
reapply, stamp or reset it. To verify its state read-only:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_database status --from-revision 0003_retrieval --to-revision 0004_access
```

For a genuinely fresh development database only:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_database inspect --from-revision base --to-revision 0001_incidents
.\.venv\Scripts\python.exe -m scripts.manage_database plan --from-revision base --to-revision 0001_incidents
# Review docs/migrations/0001_incidents.sql and its printed SHA256 before continuing.
.\.venv\Scripts\python.exe -m scripts.manage_database upgrade --from-revision base --to-revision 0001_incidents --reviewed-sha256 REVIEWED_SHA256
```

The guard stops on existing application objects, schema drift or a mismatched SQL hash.
The guard supports explicit additive revision ranges with reviewed schema snapshots and
SQL receipts. Direct online Alembic invocation and destructive initial downgrades are disabled.
No create_all or automatic startup migrations are used. Offline SQL is credential-free.
The table is incidentiq.incidents; public.incidentiq_alembic_version tracks revision state.
The app pool allows two connections, zero overflow, pre-ping, five-second connection timeout,
two-second pool wait, and three-second per-statement timeout. Use one worker on 8 GB RAM.

Opt-in PostgreSQL tests use savepoints inside a rolled-back outer transaction. They never
reset tables or delete pre-existing rows:

```powershell
$env:INCIDENTIQ_RUN_DB_TESTS = '1'
$incidentiqTestTemp = Join-Path (Get-Location) ('.pytest-db-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_database_integration.py -p no:cacheprovider --basetemp $incidentiqTestTemp
Remove-Item Env:INCIDENTIQ_RUN_DB_TESTS
# After npm run build: performs real backend process restart; retains one evidence incident.
.\.venv\Scripts\python.exe scripts/smoke.py --postgres
```

DATABASE_TEST_URL may select a separate pre-migrated development DB for opt-in tests;
otherwise they use api.env. Never put its value on a command line. Normal pytest and
scripts/smoke.py stay isolated in memory mode. Auth, tenancy and a restricted backend
database role remain a separate access-control milestone; keep this app on loopback.

## Optional Phase 2A connection probe

No database models, migrations or persistent repository are installed by this probe.
Configure DATABASE_URL in the ignored `apps/api/api.env` and save the file in the editor.
Do not paste credentials into chat, shell commands, logs or tracked files.

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -e 'apps/api[database]'
.\.venv\Scripts\python.exe scripts/verify_database.py
```

The standalone script exercises the existing dotenv loader, never prints the URL/raw
exceptions, uses SQLAlchemy/psycopg with a single unpooled connection, enforces SSL for
the probe, runs SELECT 1 in a read-only transaction, inspects client TLS status and rolls
back/closes. It does not modify `api.env` or database tables. `sslmode=require` confirms
encryption; certificate/hostname verification requires a correctly configured verify-full
policy and trusted certificate. An environment override differing from `api.env` is rejected
to avoid probing an unintended database. This probe remains read-only; API persistence
is configured separately by INCIDENTIQ_STORAGE and DATABASE_URL.

The attached workspace is `C:\Users\Jayakrishna\Documents\Projects\IncidentIQ`.
The requested `C:\Projects\IncidentIQ` was absent during inspection. No relocation was
performed. All commands below use the actual workspace; change `$repo` if you later
move the checkout. Recreate .venv after a move: virtual environments are not portable.

## First-time setup (PowerShell)

```powershell
$repo = 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
Set-Location $repo
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
& 'C:\Python315\python.exe' --version
node --version
npm.cmd --version
# Existing .venv is already Python 3.15. Only run this if creating a fresh environment:
# & 'C:\Python315\python.exe' -m venv .venv
.\.venv\Scripts\python.exe scripts/build_phase5_wheels.py
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: --find-links .cache/phase5-wheels -r apps/api/requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e apps/api
if (!(Test-Path apps/api/api.env)) { Copy-Item apps/api/.env.example apps/api/api.env }
if (!(Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
Set-Location apps/web
npm.cmd ci --no-fund --no-audit
```

Use the virtual environment executable explicitly; activation and changing execution
policy are unnecessary. This session's default `python` was 3.10.7, so do not use it.
The existing venv reports 3.15.0. Node/npm were installed but absent from this session's PATH.

## Backend (terminal 1)

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m uvicorn incidentiq.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/src
```

## Frontend (terminal 2)

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ\apps\web'
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
$env:NEXT_TELEMETRY_DISABLED = '1'
npm.cmd run dev
```

Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs.
Both servers bind to loopback only. Stop each with Ctrl+C. PostgreSQL mode needs the saved
DATABASE_URL; memory mode requires no cloud credentials.

## Configuration

| Variable | Location | Default | Meaning |
|---|---|---|---|
| INCIDENTIQ_ENV | apps/api/api.env | development | development, test, production |
| INCIDENTIQ_READY | apps/api/api.env | true | false makes readiness return 503 |
| INCIDENTIQ_STORAGE | apps/api/api.env | auto | auto, memory or postgres |
| DATABASE_URL | apps/api/api.env | unset | server-only PostgreSQL credential; never log |
| BACKEND_URL | apps/web/.env.local | http://127.0.0.1:8000 | server-only API origin |

Environment variables override API api.env values. Restart servers after configuration
changes. Do not put keys into NEXT_PUBLIC variables. No CORS settings are needed because
the health call runs in Next.js on the server. Refresh the page to update status.

## Checks

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m pytest apps/api/tests
.\.venv\Scripts\python.exe -m ruff check apps/api
.\.venv\Scripts\python.exe -m ruff format --check apps/api
.\.venv\Scripts\python.exe -m ruff check --config apps/api/pyproject.toml scripts
.\.venv\Scripts\python.exe -m ruff format --check --config apps/api/pyproject.toml scripts
.\.venv\Scripts\python.exe -m pip check
Set-Location apps/web
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
Set-Location ../..
.\.venv\Scripts\python.exe scripts/smoke.py
```

Manual acceptance: with API running, page says Connected / backend ready; set
INCIDENTIQ_READY=false and restart API for not-ready; stop API for unavailable.
`Invoke-RestMethod http://127.0.0.1:8000/health/live` returns alive. Ready is HTTP 503
when disabled; PowerShell reports non-success responses as errors.

## Dependency updates and troubleshooting

For intentional backend updates, edit pyproject.toml, install `-e 'apps/api[dev]'` with
`--only-binary=:all:`, run all checks, then regenerate the lock with `pip freeze --exclude
incidentiq-api` (UTF-8). For frontend updates, edit package.json and use npm install,
review package-lock.json, then run checks. Commit both manifests and locks.
Binary-only installation intentionally fails if a compatible Python 3.15 wheel is absent;
investigate that specific dependency rather than downgrading silently. Phase 5 adds the
documented narrow exception for PyYAML 6.0.3 (pure Python) and zstandard 0.25.0 (existing
Visual Studio C++ tools), built by `scripts/build_phase5_wheels.py`. Fresh Windows setup
requires those build tools. See [workflow setup and compatibility evidence](phase5-investigations.md).

Git 2.37 reported unsafe ownership in this execution environment. Confirm repository
ownership locally before changing trust settings; no global Git configuration was modified.
Do not run builds concurrently on an 8 GB machine. Next.js build worker count is one,
and production builds use webpack to reduce native bundler variability on Windows.

The smoke script starts temporary servers on ports 18000 and 13000, checks all three
connectivity states, incident create/list/detail/validation through the Next.js proxy,
restart data loss and unavailable-API forwarding, then stops its processes. Run it after building.
If Node is installed elsewhere, set `$env:NODE_EXE = (Get-Command node).Source` first.

Known toolchain warnings: ESLint 9.39.5 is marked unsupported by npm; current Next.js
React and accessibility plugins do not declare ESLint 10 compatibility. Keep the mutually
compatible version until those plugins support 10; do not use --force or legacy-peer-deps.
Starlette 1.9 emits a deprecation warning for its HTTPX TestClient path. HTTPX 0.28.1
still executes successfully; migrate test transport deliberately when compatibility is verified.

## Incident workflow

Run both servers, open the home page, fill in title/description/service/severity, and
create an incident. It appears in the list and its details open automatically. Select
any title to load details. Refresh incidents reloads the list; failed requests have
error/retry states. PostgreSQL incidents survive restart/reload; memory incidents do not.
The page reports the selected storage mode. Use one worker on this development machine.
Created/updated timestamps and IDs are assigned by the backend. Status starts open;
editing and transitions are not implemented. See [API contracts](api.md).

Frontend tests compile with the existing TypeScript compiler into ignored `.test-build/`
and run serially using Node's built-in runner. React Testing Library/jsdom exercise DOM
interaction without a browser download. Test dependencies are dev-only; run `npm.cmd ci`
after pulling dependency-lock changes. Python runtime/migration packages are pinned in the backend lock.

## Phase 2B

Approved live migration and validation are complete. See [measured results](phase2b-live-validation.md).
The [ingestion/migration runbook](phase2b-ingestion.md) records the historical first application.
The guard now requires explicit revision ranges; earlier Phase 2A command transcripts
are historical. Use `python -m scripts.manage_database` from the repository root with
the venv Python. API startup performs neither migrations nor ingestion.

Offline commands:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests -m 'not database' -q
.\.venv\Scripts\python.exe -m scripts.manage_database plan --from-revision 0001_incidents --to-revision 0002_logs
```

Log integration tests require `INCIDENTIQ_RUN_LOG_DB_TESTS=1` and approved 0002. They roll
back invented rows; they never migrate/create/reset tables. Leave opt-in variables unset
in CI. No new dependencies or log UI are introduced.
