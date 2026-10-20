# Native Windows developer setup

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
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r apps/api/requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e apps/api
if (!(Test-Path apps/api/.env)) { Copy-Item apps/api/.env.example apps/api/.env }
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
Both servers bind to loopback only. Stop each with Ctrl+C. No cloud credentials needed.

## Configuration

| Variable | Location | Default | Meaning |
|---|---|---|---|
| INCIDENTIQ_ENV | apps/api/.env | development | development, test, production |
| INCIDENTIQ_READY | apps/api/.env | true | false makes readiness return 503 |
| BACKEND_URL | apps/web/.env.local | http://127.0.0.1:8000 | server-only API origin |

Environment variables override API .env values. Restart servers after configuration
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
investigate that specific dependency rather than downgrading silently.

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
error/retry states. Restarting/reloading the backend clears every incident. Use one worker.
Created/updated timestamps and IDs are assigned by the backend. Status starts open;
editing and transitions are not implemented. See [API contracts](api.md).

Frontend tests compile with the existing TypeScript compiler into ignored `.test-build/`
and run serially using Node's built-in runner. React Testing Library/jsdom exercise DOM
interaction without a browser download. Test dependencies are dev-only; run `npm.cmd ci`
after pulling dependency-lock changes. No additional Python packages are required.
