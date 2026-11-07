# Local completion — 2026-11-06

Update 2026-11-07: GitHub backend/frontend CI passed at
[16355d4](https://github.com/JK578/Jai/actions/runs/42350402461). The user deferred
visual/mobile QA and selected [Phase 8 quality evaluation](phase8-quality.md).
Earlier statements below describe the narrower verification available at those milestones.

Access control, Phase 6 MCP, and the local Phase 7 delivery workflow are implemented.
Phase 5 now has an authenticated browser workspace for incidents, source logs, semantic
search, private investigation history, human approval and approved JSON download.
Cloud deployment is outside the user-selected scope.

## Executed evidence

- [Release drill](local-release-validation.json): production Next.js and FastAPI;
  login, cookie proxy, logout, cross-origin rejection, immediate token revocation,
  tenant isolation, real MCP stdio, digest-bound approval and configuration recovery.
- [Integrity audit](access-integrity.json): exact revision 0004 schema/RLS policies,
  restricted runtime privileges, unchanged original tables and unrelated relation metadata.
  All 2,000 events and retrieval documents retain their fingerprint.
- 215 offline backend tests passed on November 7; six rollback-only PostgreSQL tests
  passed in the preceding release verification.
- Frontend lint, TypeScript, tests and optimized production build passed. Component
  tests cover explicit approval carrying the displayed digest.

The final drill made zero paid model calls. Historical live evidence remains in
[Phase 4](phase4-completion.md) and [Phase 5](phase5-investigations.md). The eight-query
retrieval baseline remains 7/8 hit@5 hybrid/vector and 4/8 keyword; it is a small evaluation.

## Open locally

Run one API worker from the repository root:

```powershell
.venv/Scripts/python.exe -m uvicorn incidentiq.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```powershell
cd apps/web
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. Paste the token from ignored `.cache/access/login.txt`
into the sign-in form. It expires after 24 hours. The session cookie is HttpOnly and
SameSite=Strict, with Secure on HTTPS. Tokens never appear in session JSON or bundles.

Issue a replacement for the tenant in [the provisioning receipt](access-provisioning.json):

```powershell
.venv/Scripts/python.exe -m scripts.access_admin issue --tenant-id <tenant-uuid>
```

This writes a private login file and prints only non-secret metadata. Add `--read-only`
for a viewer. Revoke by returned user ID using `revoke --user-id <user-uuid>`. Registry
hashes are checked on every request. Public hosting would need a separately reviewed
identity provider and session lifecycle; the current credentials are issued by a local operator.

## Controls

The API uses restricted login `incidentiq_app`, inheriting NOLOGIN group
`incidentiq_runtime`. Transaction-local tenant IDs and RLS constrain incidents, logs,
provenance and retrieval. Owner credentials remain for trusted operator CLIs only.
Runtime TLS verifies the hostname using Supabase's public CA plus standard roots.
Ignored `.cache/access/` contains private credentials and trust material.

Investigations are private per tenant/user under `.cache/investigations-web/`. Demo is
the default and labels synthetic evidence. Live mode uses scoped retrieval, one concurrent
model operation, up to $0.02 reserved per start/retry and a persistent $0.10 daily reservation
ceiling per user. Reservations are not refunded. Semantic search reserves a conservative
embedding allowance. Trusted CLIs have separate budgets; this is not an account-wide OpenAI cap.
One explicit retry is permitted. Suggested operational commands are never executed.

Both proxy and API bound request bodies to 64 KiB. Authenticated API calls are limited
to 120/minute per user in the single worker. Pages/results are bounded. Request logs
record route templates, status and duration; tokens, query values, bodies, evidence and
database/provider errors are excluded. Cloud investigation tracing is disabled.

## Verify and recover

```powershell
.venv/Scripts/python.exe -m scripts.validate_access_integrity
.venv/Scripts/python.exe -m scripts.validate_local_release
```

The drill requires a current frontend build, available ports 8001/3001 and access to
the development database. It creates private demo reports and temporary credentials in
a separate ignored registry, preserving your login token. Child processes stop on exit.
It verifies readiness 503 with a disabled candidate configuration, restores the secure
configuration, then verifies readiness 200 and unauthenticated 401. This is configuration
rollback. A separate backend source-artifact rollback drill now also passes; see below.
Do not remove RLS/authentication to restore an insecure older application.

## Backend artifact rollback — 2026-11-07

`scripts.local_release` creates a source snapshot under ignored `.cache/releases/` with
SHA256 hashes of every packaged file and a manifest hash. Only API source, migrations,
Python operator scripts and dependency/configuration metadata are included; environment
files, credentials and private state are excluded. Verification rejects changed files,
extra files and escaping paths before execution. Keep the expected manifest hash separately.

```powershell
.venv/Scripts/python.exe -m scripts.local_release
.venv/Scripts/python.exe -m scripts.validate_artifact_rollback
```

The drill runs a verified secure snapshot A, a separate fault-injected candidate B,
then restores A on port 8002. Readiness is 200, 503, 200; authenticated reads work and
unauthenticated reads return 401 throughout. Import probes verify execution from each
artifact rather than the editable checkout. The same private investigation checkpoint
and report digest survive the candidate and rollback. The paused draft is never published.
See [executed evidence](artifact-rollback-validation.json). No schema changes or paid
model calls occur, and your normal token registry is untouched.

Set `INCIDENTIQ_DATA_DIR` to an absolute directory outside release artifacts to retain
investigation checkpoints and the daily budget ledger across releases. It defaults to
the checkout's `.cache` during development. Keep `INCIDENTIQ_TOKEN_REGISTRY` pointing
to the separate absolute credential registry path as configured by bootstrap.

These are backend Python source artifacts using the existing shared Python environment.
This does not validate dependency-environment rollback, frontend artifact rollback,
database downgrades or a historical production release. Those remain outside this drill.

Browser discovery returned no available browser. HTTP/rendered HTML and component
interaction checks passed; visual/mobile QA remains unverified. GitHub Actions has not
run remotely for these changes. No cloud deployment was performed.

## Standalone frontend rollback — 2026-11-07

The frontend now builds as a standalone package with its traced Next.js dependencies.
Manifest verification, credential-file exclusion and static-asset copying are covered by
tests. A real package A / fault-injected B / restored A drill returned 200/503/200 and
preserved the authenticated session across rollback. Protected API forwarding, the
tenant catalog, six static assets and logout passed without paid model calls.
Next.js resolved inside the packages without NODE_PATH or the checkout's node_modules.
See [the receipt](frontend-rollback-validation.json) and [packaging runbook](phase7-frontend-release.md).

Final follow-up checks: 211 offline backend tests, 15 frontend tests, Python lint/format,
frontend lint/types/standalone build and pip consistency passed. The Node executable and
Python environment were shared in that frontend drill. The separate Python environment
drill below extends this verification. Visual/mobile browser QA remains unavailable.

## Isolated Python environment rollback — 2026-11-07

All 61 exact dependency pins were downloaded once and sealed with per-wheel hashes.
Two fresh environments then installed offline using `--no-index --require-hashes`.
Installed versions, pip consistency, dependency import origins and environment files
were verified independently of development site-packages. An altered dependency in
the candidate was rejected before execution; the original environment was restored.

Authenticated API reads, the same private investigation checkpoint/report digest and
a seeded daily-budget reservation survived restoration. Missing credentials and
unauthorized approval remained denied. The report stayed unpublished. No database
migrations, incident writes or paid model calls occurred. See [the receipt](python-rollback-validation.json)
and [environment runbook](phase7-python-release.md). Latest backend checks: 215 offline
tests plus lint and formatting passed.

The host Python interpreter/standard library and Node executable remain shared. This
does not test upgrades/downgrades between dependency or host-runtime versions. Browser
visual/mobile QA remains blocked by no connected browser; remote GitHub CI has not run
for these local changes. Cloud deployment remains outside the requested scope.
