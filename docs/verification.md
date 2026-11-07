# Verification record

## Phase 8 offline quality evaluation — 2026-11-07

Visual/mobile QA is deferred at the user's explicit request. Prior GitHub backend and
frontend CI passed at [16355d4](https://github.com/JK578/Jai/actions/runs/42350402461).
Phase 8 adds report-bound review annotations and metrics for finding support, citation
support and expected fact coverage. Fourteen synthetic cases match their expected
outcomes; these validate scorer mechanics, not live model accuracy. Changed question,
report or evidence invalidates annotations; absent/incomplete reviews cannot pass.
233 offline backend tests passed. A saved real report passed structural checks and has
a private review template; semantic scores remain null pending human annotation.
No model calls, database changes or publication actions occurred.

## GitHub CI handoff — 2026-11-07

Local pre-push checks passed: 217 offline backend tests, project-configured Python
lint/format and the real HTTP frontend/backend smoke. The frontend previously passed
15 tests, lint/types and standalone build. The workflow now passes Ruff's project
configuration explicitly to avoid working-directory-dependent import classification.
A credential check scans indexed file contents without printing matched secret values;
the same check is included in CI. Runtime env files and release caches stay ignored.
Remote execution results are tracked in [GitHub Actions](https://github.com/JK578/Jai/actions).
Browser discovery still returned no connected browser, so visual/mobile QA is pending.

## Isolated Python environment rollback — 2026-11-07

61 locked distributions installed offline into two fresh environments with required
wheel hashes. Installed versions/import origins, pip consistency and file manifests
were checked. A modified candidate dependency was rejected before execution and the
verified baseline was restored. Authenticated API reads, private checkpoint/report
digest and seeded budget reservation survived; missing credentials and unauthorized
approval remained denied. The draft stayed unpublished. No paid calls or schema changes.
215 offline backend tests, lint and formatting passed. See [the receipt](python-rollback-validation.json)
and [runbook](phase7-python-release.md). Host runtime/version migration and visual/mobile
browser checks remain unverified. Earlier records below describe their own narrower scope.

## Standalone frontend rollback — 2026-11-07

Verified package A, fault-injected B and restored A returned HTTP 200/503/200. The same
session survived rollback; authenticated incident/provenance proxies, six static assets
and logout passed. Next.js resolved from each package's bundled node_modules, with no
NODE_PATH or API/database credentials in the frontend environment. Environment files
are excluded and all packaged files are hash-verified. No paid model calls occurred.
211 offline backend tests, 15 frontend tests, lint/types/format/standalone build and pip
consistency passed. Browser discovery still returned no browser. Node/Python runtime
version rollback and remote CI remain unverified. See [the receipt](frontend-rollback-validation.json)
and [runbook](phase7-frontend-release.md). Earlier entries below are historical.

## Backend artifact rollback — 2026-11-07

Manifest-verified source artifact A, fault-injected candidate B and restored A passed
readiness 200/503/200 on a separate loopback port. Authentication remained active, imports
resolved inside the artifacts and the same private investigation checkpoint/report digest
survived all three processes. External data-directory configuration now keeps workspace
state independent of source location. No paid calls or schema changes were made.
208 offline backend tests, lint and formatting passed. Browser discovery still returned
no browser; frontend artifact/dependency-environment rollback remains unverified.
See [the artifact receipt](artifact-rollback-validation.json) and [runbook](local-completion.md).

## Current local verification — 2026-11-06

Access control, MCP and authenticated workspace integration are implemented. Final checks:
205 offline backend tests, six rollback-only PostgreSQL tests, 15 frontend tests,
frontend lint/types/production build, Python lint/format and pip consistency passed.
The real local release drill verified login/logout, tenant isolation, revocation, MCP,
digest-bound approval and configuration rollback with zero paid model calls.
Original source tables and all 2,000 retrieval documents retain their fingerprints.
See [the current report](local-completion.md), [release receipt](local-release-validation.json)
and [integrity audit](access-integrity.json). Older entries below are historical.
Visual/mobile browser QA, older-binary rollback and remote CI remain unverified;
cloud deployment is outside the selected local-only scope.

## Phase 5 complete — 2026-11-06

Implemented the LangGraph retrieval/drafting/review/publication workflow with durable
local SQLite checkpoints, conservative per-run budgets and an external-call journal.
Human approval is bound to the exact report/evidence hash. Rejection and unsupported
model action fields cannot publish; no operational command or incident write is exposed.

192 offline backend tests passed, including 22 new workflow tests. All 6 rollback-only
PostgreSQL tests passed in 37.53 seconds. Ruff lint/format (72 files), pip consistency,
backend readiness and frontend HTTP passed. Source table hashes, unrelated metadata
and all 2,000 persisted retrieval vectors remain unchanged: [integrity](phase5-integrity.json).

Fresh-process CLI checks verified synthetic approval/rejection without duplicate paid
nodes. One live investigation returned a valid report with five verified citations and
reopened unchanged; it remains awaiting human review, unpublished. Initial conservative
budget was $0.02; 16,158 micro-USD remains. Actual billing was not measured.
See [sanitized validation](phase5-validation.json) and [completion/setup](phase5-investigations.md).

LangGraph dependencies required two documented source-built compatibility wheels on
Python 3.15: pure-Python PyYAML 6.0.3 and zstandard 0.25.0 built with existing Visual Studio
C++ tools. No Python downgrade or compiler installation occurred. Both runtime import/
compression checks and regressions passed. CI setup was updated; a new remote CI result
is not claimed. Checkpoints, excerpts, local reports and compatibility wheels are ignored.

## Phase 4 complete — 2026-11-06

The budgeted CLI indexed all 2,000 source events using 886 distinct OpenAI embeddings.
Replay detected the matching snapshot, performed no API calls or replacement writes and
retained the same full index fingerprint. Two fresh CLI processes returned the same 2,000
persisted vectors. Fixed source-derived labels for eight real queries produced top-5
relevant hits on 4/8 keyword, 7/8 vector and 7/8 hybrid queries; all returned citations
matched source evidence. The missed paraphrase and evaluation limits are documented.

170 offline tests and all 6 rollback-only PostgreSQL tests passed. Ruff lint/format
(65 files), pip consistency and backend readiness passed. Final protected source table
hashes and unrelated relation metadata match the reviewed baseline. Final retrieval
storage is 6,373,376 bytes; measured incremental worker peak working set is 82,853,888
bytes. The total 12,647 reported embedding tokens imply about $0.00025294 at checked
pricing; actual account billing/balance was not queried. See [completion and evidence](phase4-completion.md).

## Retrieval migration applied — 2026-11-06

Following explicit user approval, the guarded `0002_logs:0003_retrieval` upgrade applied
the exact reviewed SQL hash. Target schema checks passed; protected data/structure and
unrelated relation metadata remained unchanged. The rollback-only PostgreSQL retrieval
integration test passed: 1 test in 8.35 seconds. It exercised real FTS/pgvector search,
atomic publication/replay, citations and index-only deletion with original events retained.

Final read-only verification confirmed revision 0003_retrieval, vector 0.8.2 in extensions,
2,000 original events and zero retrieval documents (no synthetic index rows survived).
Database size was 12,711,603 bytes after migration/test allocation. Backend readiness
returned ready with PostgreSQL. Receipt: [0003 applied](migrations/0003_retrieval.applied.json).
No paid embeddings or real-corpus indexing were performed; those remain Phase 4 work.

## pgvector enabled — 2026-11-06

Following explicit user approval, `scripts.enable_vector` applied only the reviewed
extension prerequisite. Verified vector 0.8.2 in schema `extensions`; database revision
remains 0002_logs. Before commit, the guarded operation verified the current target and
baseline, source schema/RLS/grants, all protected table data/structure hashes and unrelated
relation metadata. The comparison passed. Receipt: [vector enablement](migrations/0003_vector_enabled.json).
Migration 0003, live retrieval tests and embedding/index publication remain pending.
No OpenAI calls were made. The helper passed Ruff lint/format checks; its initial network
sandbox attempt failed before changes and the permitted outside-sandbox execution succeeded.

## Phase 4 PostgreSQL preparation — 2026-11-06

Prepared `PostgresRetrievalIndex`, additive migration 0003 and its revision snapshot,
separate vector-extension prerequisite SQL, read-only capability probe and opt-in
rollback integration test. Full offline backend regression: 167 passed, 6 database
tests deselected. Ruff lint and formatting (60 files) passed; pip dependency consistency
passed. Existing Starlette/HTTPX deprecation warning remains.

Read-only Supabase preflight confirmed revision 0002_logs, 2,000 events, no messages
over the embedding limit, database size 12,449,459 bytes, and vector 0.8.2 available but
not installed. The guarded source schema/RLS/grant inspection passed and captured
current protected-data/structure and unrelated-metadata hashes. Network operations
required permitted execution outside the sandbox; initial sandbox attempts failed safely.

The proposed 0003 table and SQL behavior are tested offline; the new PostgreSQL retrieval
integration test has not run. No extension, migration, index publication/deletion or paid
embedding was executed. See [SQL, hashes, baseline and application procedure](phase4-migration-review.md).

## Phase 4 first slice — 2026-11-06

Retrieval contracts, file-scoped reference index (BM25 + exact cosine + reciprocal rank
fusion), bounded OpenAI embeddings adapter, and synthetic evaluation implemented.
Full offline backend regression: 146 passed, 5 database tests deselected; Ruff lint passed,
formatting passed for 54 files. Existing Starlette/HTTPX deprecation warning remains.
The 29 retrieval tests cover citations, stable rebuilds, deletion, scope/model isolation,
atomic failure across batches, rank fusion, vector validation, safe provider failures,
request payloads, response ordering and budget handling. The deterministic evaluation
receipt is [phase4-evaluation.json](phase4-evaluation.json).

No paid embeddings or database changes were performed. The curated-vector fixture
validates ranking mechanics, not real model quality. Phase 4 remains in progress pending
persistent indexing and real-corpus evaluation; see [remaining work](phase4-retrieval.md).

## Phase 3 — 2026-11-06

Live follow-up: the configured `gpt-5.6-luna` returned a successful short response to one
synthetic CLI prompt with reasoning disabled and a configured $0.02 invocation budget.
Missing non-secret model settings were restored; the key was never displayed. Actual
billed cost and account credit balance were not queried. Gateway tests after adding
explicit reasoning configuration: 27 passed.

Provider-independent model gateway implemented with mock and OpenAI Responses adapters.
Full offline regression: 116 passed, 5 database tests deselected. The 26 new tests cover
provider contracts, budget reservations/refunds/concurrency, request bounds, HTTP payloads,
sanitized failures, timeouts and malformed/incomplete/refused/oversized responses.
See [implementation and limitations](phase3-model-gateway.md). Live paid OpenAI inference
was not performed; HTTP behavior is tested using MockTransport. No schema or frontend
changes are part of this milestone.
Ruff lint and formatting (48 files), pip dependency consistency, and the mock CLI smoke
check passed. No dependency downloads were needed.

## Phase 2B recheck — 2026-11-06

The implemented milestone remains complete. Rechecked against the running development API:

- Offline backend suite: 90 passed, 5 database tests deselected; existing Starlette/HTTPX
  deprecation warning remains.
- Ruff lint passed; formatting check passed for all 44 Python files.
- Backend readiness returned `ready` with PostgreSQL storage.
- Full log pagination returned exactly 2,000 unique persisted event IDs, with advancing cursors.
- Dataset catalog and ingestion history reads succeeded: three completed runs, each
  accounting for 2,000 processed lines, with zero rejects. The initial run inserted
  2,000 events; both subsequent runs recorded 2,000 duplicates and zero inserts.

The original live report retains the database integration, crash/recovery, fencing,
restart and resource measurements. Those drills and database tests were not rerun
for this recheck. No migration or ingestion was performed, and no application code
change was needed. Both development servers were left running.

Current milestone, 2026-10-21: [Phase 2B controlled live validation](phase2b-live-validation.md)
is complete. Migration 0002 applied; 90 offline tests and 5 PostgreSQL tests passed in
separate runs. There are 2,000 events, zero new events on replay, zero failed/incomplete
audit runs, and verified real crash recovery, worker fencing and process restart.
Measured total log storage is 1.21875 MiB; maximum incremental worker working set is
5.75 MiB. Original incident count/fingerprint and unrelated metadata are unchanged.
No Phase 2C work is authorized. Entries below describe historical milestones.

Latest milestone: [Phase 2A persistent storage and migration verification](phase2a-storage.md).

Latest milestone: [Phase 1B completion and verification](phase1b-completion.md).

This records the initial implementation run. For the subsequent review, minor fixes,
eight-test result and current readiness recommendation, see [Phase 1 review](phase1-review.md).

Executed on native Windows, 2026-10-19, in the attached repository.

## Environment and installation

- Existing `.venv`: CPython 3.15.0. No Python downgrade or venv replacement.
- Node v24.22.0, npm 11.19.1, accessed from `C:\Program Files\nodejs`.
- Default shell `python` was 3.10.7 and was not used to install or test the project.
- Binary-only backend dependency installation succeeded, including
  `pydantic_core-2.50.1-cp315-cp315-win_amd64.whl`.
- FastAPI 0.149.0, Pydantic 2.14.1, Uvicorn 0.54.0, pytest 9.1.1, Ruff 0.17.1.
- npm installation succeeded: Next.js 16.4.2, React 19.3.1, TypeScript 5.9.3,
  Tailwind 4.3.3, ESLint 9.39.5. Exact resolutions are in package-lock.json.

## Executed checks

| Check | Actual result |
|---|---|
| pytest apps/api/tests | 5 passed; one Starlette HTTPX deprecation warning |
| Ruff lint | Passed |
| Ruff format check | Passed |
| pip check | No broken requirements found |
| npm run lint | Passed, zero warnings after PostCSS export fix |
| npm run typecheck | Passed |
| npm run build | Passed; dynamic home page, one build worker |
| python scripts/smoke.py | 3 scenarios passed against real FastAPI and built Next.js servers |

Backend tests cover response schema, request logging, environment overrides, invalid
configuration, readiness disabled, startup/shutdown readiness and independent liveness.
The smoke test checks API HTTP codes and rendered frontend status for ready, not-ready,
and stopped-API states. These are HTTP/rendering checks, not screenshot or browser tests.

## Limitations and warnings

- Browser discovery returned no available browser. Visual/mobile layout and interactive
  browser verification were not performed.
- Git reports an ownership mismatch. No global trust settings were changed; no commit
  was created. Filesystem checks were used to inspect changes.
- GitHub Actions workflow was authored, but has not run remotely in this session.
- ESLint 9 upstream support has ended; installed Next.js React/accessibility plugins still
  exclude ESLint 10. Upgrade together when mutually compatible; no peer constraints bypassed.
- Starlette 1.9 warns that HTTPX TestClient support is deprecated. Tests still pass.
- npm emitted an unapproved optional install-script notice for `unrs-resolver`. No scripts
  were manually approved; lint/type/build passed with the installed packages.
- Windows emitted a pre-existing command-shell AutoRun registry parsing notice during
  npm commands. Commands completed successfully; registry settings were not modified.
- Package installation required network approval after sandbox network access failed.
- This verifies the foundation only. Supabase, SQLAlchemy, model inference, LangGraph,
  MCP and hybrid retrieval compatibility remain untested and unimplemented.

## Milestone boundary

Foundation implementation is complete. Next proposed milestone is Phase 1B: a typed
incident domain and an explicitly ephemeral create/list/detail vertical slice.
Await approval before starting it.
# Phase 2B offline verification — 2026-10-20

Phase 2B code, tests, docs and additive migration 0002 are prepared. Live application and
ingestion are explicitly pending approval. Final backend suite: **90 passed, 5 skipped**;
frontend: **12 passed**, lint/typecheck/build passed. Python lint/format/compile and pip
consistency passed. Memory-only loopback smoke passed. No live database operation was
performed. See [completion evidence](phase2b-completion.md) and the
[guarded application runbook](phase2b-ingestion.md). Earlier entries below are historical.
