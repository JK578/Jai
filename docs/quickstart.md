# Run IncidentIQ yourself

Windows PowerShell is the supported fresh-machine setup below. One launcher starts
both services, prints their URLs and stops both when you press Ctrl+C. No activation
script or PowerShell execution-policy change is needed.

## 1. Prerequisites and one-time setup

Install Git, Python **3.15**, Node **24** with npm **11**, and Visual Studio C++ Build
Tools (Desktop development with C++ and a Windows SDK). C++ tools are needed to build
the pinned zstandard compatibility wheel on Python 3.15; setup does not install a compiler.
Dependency installation requires internet access. Run the app from a writable local folder.

```powershell
git clone --branch feature/incident-domain https://github.com/JK578/Jai.git
cd Jai
py -3.15 scripts/dev.py setup
```

Setup creates `.venv`, builds the two required compatibility wheels, installs locked
Python packages and frontend dependencies, and builds the frontend. It copies example
environment files only when the real files do not exist. Existing credentials are preserved.
Do not copy `.venv`, `node_modules` or `.next` from the old machine.

If your Python installation has no `py` launcher, replace `py -3.15` with the path to
your Python 3.15 executable. Setup leaves the configured database untouched: no migrations,
ingestion, role changes or model calls run automatically.

## 2. Quick basic demo — no credentials

```powershell
py -3.15 scripts/dev.py run --basic
```

Open **http://127.0.0.1:3000**. Create an incident, refresh the list and open its details.
This mode is incident CRUD only: no sign-in, database, log search or investigations.
Incidents disappear when the backend stops. It does not change your saved full-mode settings.

## 3. Full flow — reuse the existing development database

This mode uses the same database and tenant as the original setup, so incident changes
are shared with that development environment. A new application environment is not a
new database. Use the existing pre-migrated database with its logs/index already loaded.

Transfer these files privately from the original environment into the new checkout:

- `apps/api/api.env` — owner/runtime URLs, model configuration and optional provider key.
- `.cache/access/ca-bundle.pem` — the trusted CA bundle referenced by the runtime URL.

Do not put credentials in Git or chat. You do not need to copy old login tokens,
`runtime-url.pending`, private reports or the entire cache.

Rebase old machine paths to this checkout, then issue a fresh token for the **same** tenant:

```powershell
py -3.15 scripts/dev.py configure
$tenant = (Get-Content docs/access-provisioning.json | ConvertFrom-Json).tenant_id
py -3.15 scripts/dev.py token --tenant-id $tenant
py -3.15 scripts/dev.py run
```

Use the tenant from that receipt only when reusing its existing database. Configuration
rebasing preserves database passwords and verify-full TLS, updates local CA/token/data
paths, and aligns frontend authentication. It does not rotate roles or apply migrations.
If shell environment variables override the copied settings, remove those stale overrides
or use a fresh terminal before running.

Open **http://127.0.0.1:3000** and paste the token from `.cache/access/login.txt` into
the sign-in form. Tokens expire after 24 hours; repeat the `token` command for a replacement.
The new user can see tenant incidents/logs; investigation history is private to that user.

### Suggested manual test flow

1. Sign in and create an incident. Refresh/open its detail to confirm persistence.
2. Open Logs & search, inspect source rows and try the free literal text filter.
3. Open Investigations, enter a question and choose **Demo** first. Demo uses synthetic
   evidence and no model credits; it still checks access to the configured source file.
4. Inspect the draft findings, source evidence and uncertainty. Approve and download
   the report, or reject a separate draft to test the other branch.
5. Stop with Ctrl+C, rerun the launcher and confirm incident/history persistence.
6. Optionally test semantic search or **Live AI** with a valid provider key. These use
   credits and the application's reservation limits. Live AI is never selected automatically.

For a completely new database, use the reviewed migration, ingestion, indexing and access
provisioning runbooks. Do not run bootstrap or reset commands against the existing shared
database just to start a new machine. New-database provisioning is deliberately not automated here.

## Options and troubleshooting

```powershell
# Use other ports if your existing app is already running:
py -3.15 scripts/dev.py run --api-port 8001 --web-port 3001
# Start, verify HTTP readiness, and stop automatically:
py -3.15 scripts/dev.py run --basic --check --api-port 8001 --web-port 3001
```

API docs are at **http://127.0.0.1:8000/docs** with the default ports. Private logs are
in `.cache/dev/api.log` and `.cache/dev/web.log`. Startup errors or Ctrl+C stop only the
launcher-owned processes. Busy ports are reported; unrelated running services are not killed.

If full mode is not ready, check database network access, the copied CA file, runtime
credentials and the local token registry. An expired token affects sign-in, not database
readiness. If a build is missing, rerun `setup`; it reinstalls dependencies and rebuilds
the frontend, so first stop applications using this checkout. For code edits, rebuild
the frontend before rerunning this launcher; it serves the production build, not hot reload.

This setup targets Windows. Other operating systems need an OS-specific compatibility
wheel build path; the current wheel builder uses Windows Visual Studio tools.
