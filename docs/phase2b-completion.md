# Phase 2B offline completion report

Historical report. Update 2026-10-21: migration and controlled live validation are now
complete; see [current results](phase2b-live-validation.md). The checks below describe
the earlier offline approval boundary.

Date: 2026-10-20. Implemented through the requested approval boundary. **No migration
0002 application, live schema inspection, database writes or public dataset ingestion
were executed.** Ready for review of the proposed migration, not a claim of live completion.

## Executed checks

| Check | Result | Evidence / limitation |
|---|---|---|
| Backend default suite | PASS | `python -m pytest apps/api/tests -q`: 90 passed, 5 skipped, 1 warning, 3.19 s |
| PostgreSQL integration | NOT VERIFIED | Five opt-in tests skipped (two incidents, three logs); require explicit post-migration approval |
| Parser and source validation | PASS offline | Pinned manifest, synthetic 2000-line artifact, malformed lines/encoding/dates, exact line bound/CRLF, oversized-line drain, checksum-before-DB, private snapshot, mocked download/redirect/error cleanup |
| Idempotency and retry | PASS offline | Equal messages on different lines preserved; repeated runs add no events; retry before commit and lost acknowledgement after commit preserve counters/checkpoints |
| Crash recovery and fencing | PASS offline | Simulated process death/rollback, committed checkpoint resume, active-worker rejection, expired lease takeover, stale insert/fail rejection, retry exhaustion and failed-run resume |
| Adapter transactions/conflicts | PASS offline | Session commit/rollback, parameterized INSERT/substring filter, digest conflict rollback, sanitized errors and owner-token omission tested using mocks |
| Migration guards | PASS offline | Source/target ancestry, status at 0001 with 0002 present, reviewed hash/baseline refusal, protected-data/unrelated-metadata mismatch rollback, immutable 0001 and additive SQL regression checks |
| Python lint | PASS | `ruff check --config apps/api/pyproject.toml apps/api scripts` |
| Python formatting | PASS | `ruff format --check --config apps/api/pyproject.toml apps/api scripts`: 41 files formatted |
| Python compilation | PASS | `compileall -q apps/api/src apps/api/migrations scripts` |
| Python static type checker | NOT CONFIGURED | Existing project has no mypy/pyright task; annotations/compilation do not establish static type-check success |
| Installed dependency consistency | PASS | `pip check`: no broken requirements; no new packages installed, Python 3.15 retained |
| Frontend lint / TypeScript | PASS | `npm.cmd run lint`; `npm.cmd run typecheck` |
| Frontend tests | PASS | `npm.cmd test`: 12 passed, 0 failed |
| Production build | PASS | Next.js 16.4.2, webpack, one worker; rerun succeeded after initial sandbox EPERM accessing Next.js local config |
| Frontend/health regression | PASS | `python scripts/smoke.py`: ready/not-ready/unavailable states; incident create/list/detail/validation; memory restart reset; stopped-API proxy 502 |
| Live persistence/recovery/concurrency | NOT VERIFIED | Rollback tests and offline fakes cannot establish process restart durability or real PostgreSQL interleavings |
| Storage <10 MiB / incremental worker RAM <100 MiB | NOT VERIFIED | Bounded source/line/batch/error/audit limits implemented; live PostgreSQL/Windows measurements await approval |
| Secret review | PASS for working files | Pattern scan of 95 source/config/doc files found no candidate secrets; api.env ignored/untracked; raw cache ignored; no claim of a complete historical secret audit |
| Migration SQL generation/review | PASS offline | Five additive tables; no incidents/unrelated DDL or drops; SQL hash below |

The Starlette/HTTPX TestClient deprecation remains; current tests pass. Existing ESLint 9
support warning remains documented in development instructions. No speculative dependency
replacement or Python downgrade was made. Git checks require execution outside this
sandbox because repository ownership is reported unsafe; no global trust setting changed.

## Files created or modified

Created:

- `apps/api/migrations/versions/0002_logs.py`
- `apps/api/src/incidentiq/domain/logs.py`
- `apps/api/src/incidentiq/application/{log_ingestion,log_source}.py`
- `apps/api/src/incidentiq/infrastructure/{log_models,log_repository,log_source}.py`
- `apps/api/src/incidentiq/api/logs.py`
- `apps/api/src/incidentiq/datasets/{apache_2k.json,LOGHUB-LICENSE.txt}`
- `apps/api/tests/{log_fake,test_logs,test_log_source,test_log_repository,test_logs_database,test_migration_ranges}.py`
- `apps/api/tests/fixtures/{apache_synthetic.log,README.md}`
- `scripts/{ingest_logs,migration_catalog}.py`
- `docs/migrations/{0001_incidents.schema.json,0002_logs.schema.json,0002_logs.sql}`
- `docs/adr/0007-bounded-log-ingestion.md`
- `docs/{phase2b-ingestion,phase2b-completion}.md`

Modified:

- `.github/workflows/ci.yml` (explicitly excludes database tests)
- `.gitignore`, `README.md`
- `apps/api/{.env.example,pyproject.toml,migrations/env.py}`
- `apps/api/src/incidentiq/main.py`, `apps/api/tests/test_postgres.py`
- `scripts/manage_database.py`
- `docs/{api,architecture,development,roadmap,verification}.md`

The previously reviewed `docs/phase2b-log-ingestion-plan.md` remains alongside the
implementation docs. No frontend source or dependency locks changed. Migration 0001
and its original SQL/inspection/applied receipts remain unchanged. Its source SHA256
is `2924d25751840d0b269eea9fbfd4571f6b53c70663b417758d6353de0664db61`.

## Schema, API and decisions

Five tables: log_datasets, log_files, log_ingestion_runs, log_events,
log_ingestion_errors, all under incidentiq with RLS/revoked grants. Events use deterministic
UUIDs and unique file/line identity; raw/source fields and unknown timezone are preserved.
Run checkpoints/counters/errors and events commit together; leases use DB time with
ownership fencing and one running worker. See [ADR 0007](adr/0007-bounded-log-ingestion.md).

Six read-only GET routes: `/api/v1/log-datasets`, `/api/v1/log-ingestions`,
`/api/v1/log-ingestions/{run_id}`, `/api/v1/log-ingestions/{run_id}/errors`,
`/api/v1/logs`, `/api/v1/logs/{log_id}`. Pagination and literal level/message/local-time
filters are bounded. No ingestion HTTP endpoint or new UI is introduced. Existing
incident/health contracts remain; missing log schema returns safe 503 from log reads.

SQL range `0001_incidents:0002_logs` canonical SHA256:
`d3f59a42af151a26995248cd2c1604ba8bcaa5ef30339fbf528dd75432618094`.
Review [SQL](migrations/0002_logs.sql) and follow the exact [approval runbook](phase2b-ingestion.md).
Do not use unguarded Alembic, stamp, reset or create_all. Downgrade would delete log data;
it is not approved. Future additive revisions require a reviewed schema snapshot; existing
table changes require a separate safety-policy extension.

## Remaining approval work

1. Approve live development-schema inspection and migration 0002. Stop writers, recheck
   exact source revision/schema/data baseline, apply only the reviewed SQL via the guard,
   and verify protected incidents/unrelated metadata remain unchanged.
2. Approve rollback-only database tests and public ingestion. Verify real parsing/counts,
   repeated-ingestion idempotency, worker concurrency, kill/resume and restart persistence.
3. Measure storage and worker RAM; retain non-secret evidence. At 50 audit runs, stop for
   retention review rather than deleting history automatically.

Loghub terms permit research/academic use; commercial/deployment suitability needs a
separate review. Owner-role credentials and unauthenticated loopback APIs remain development
limitations. Run-history offset pages can shift when new runs arrive; event source-line
cursors are stable. Constraint identities are compared to revision snapshots and full
definitions protected during baseline/postflight comparison; SQL review remains necessary.

Recommendation: approve the focused live-validation steps when ready. Do not proceed to
another feature milestone until post-migration evidence and resource measurements pass.
