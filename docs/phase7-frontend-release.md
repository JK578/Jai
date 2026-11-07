# Local frontend release packaging

Verified 2026-11-07: standalone A, fault-injected B and restored A returned 200/503/200.
The same authenticated session survived restoration; protected proxy calls, tenant
catalog, six static assets and logout passed. Next.js resolved inside each package.
See [the executed receipt](frontend-rollback-validation.json). No paid model calls occurred.

Next.js builds with `output: standalone`. The release snapshot contains its traced
production dependencies, server entrypoint and separately copied static/public assets.
It does not require the source checkout's `node_modules`. Node itself remains installed
on the host. No cloud hosting is configured.

From the repository root:

```powershell
cd apps/web
npm.cmd run build
cd ../..
.venv/Scripts/python.exe -m scripts.frontend_release
.venv/Scripts/python.exe -m scripts.validate_frontend_rollback
```

Packaging creates a new directory under ignored `.cache/releases/frontend/` and prints
its path and manifest SHA256. Environment files and caches are excluded. Every packaged
file is hashed; missing, altered, extra and escaping files are rejected by verification.
Keep the expected manifest digest outside the artifact. Windows symlinks/junctions are
rejected rather than publishing a package that points back into the build checkout.

To run a verified package, use the `entrypoint` in its manifest and configure these
server-only environment variables before starting Node:

```powershell
$env:PORT='3000'
$env:HOSTNAME='127.0.0.1'
$env:BACKEND_URL='http://127.0.0.1:8000'
$env:INCIDENTIQ_AUTH_ENABLED='true'
node <artifact-directory>/server.js
```

Depending on Next's tracing root, the entrypoint can instead be `apps/web/server.js`.
Do not pass OpenAI keys, database URLs or the token registry into the frontend process.
The browser sign-in flow passes a credential to the API and creates an HttpOnly cookie.

The rollback drill uses separate ports 8003/3002 and temporary read-only credentials,
preserving the normal login file. It runs package A, a separate fault-injected package B,
then A again. It checks sign-in, authenticated API forwarding, a visible tenant log
catalog, static assets, session continuity across rollback and logout. The candidate
returns 503 rather than serving private data. Each package must resolve Next.js from
its own bundled dependencies, using a minimal environment without NODE_PATH.

The fault is deliberately injected into a copy of the server entrypoint; the normal
build and baseline package are unchanged. This tests recovery from a rejected local
candidate, not compatibility with an older historical production release. It performs
no database migrations, incident writes or paid model calls. It uses the current host
Node runtime and current backend; Python environment and database rollback are separate.

HTTP and component interaction checks do not establish visual/mobile browser quality.
That verification requires a connected browser.

Separate [isolated Python environment and rollback checks](phase7-python-release.md)
are now available for the backend.
