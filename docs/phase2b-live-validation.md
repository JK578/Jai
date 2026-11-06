# Phase 2B controlled Supabase live validation

Completed 2026-10-21, following explicit authorization for the configured DEVELOPMENT
database. Migration 0002 is applied and live validation passed. No Phase 2C work was
performed. The original offline report remains historical evidence.

## Preflight and migration

| Check | Result |
|---|---|
| Secure configuration and target | PASS: api.env loads without an overriding URL; development environment and previously approved Supabase project match; values withheld |
| Connection / SSL / runtime | PASS: SELECT 1; psycopg reports SSL in use with require policy; Python 3.15.0, SQLAlchemy 2.1.5, psycopg 3.3.6 |
| Source revision and schema | PASS: 0001_incidents, only incidents in the owned schema; types, keys, checks, indexes, RLS and grants validated |
| Existing incidents | PASS: count 1, integrity SHA256 recorded below |
| Unrelated objects | PASS: 186 relations; metadata hash matches historical Phase 2A baseline |
| Reviewed 0002 SQL | PASS: exact reviewed hash; five additive tables/indexes/RLS/revokes and dedicated version update; no incident/unrelated DDL or drops |
| Guarded apply | PASS: baseline rechecked under locks; transaction committed only after target schema and protected data/metadata verification |
| Post-apply / final status | PASS: 0002_logs; all six owned tables match the revision snapshot, including the partial worker index and FK/unique/check constraints |

Applied SQL SHA256 (canonical LF text):
`d3f59a42af151a26995248cd2c1604ba8bcaa5ef30339fbf528dd75432618094`.
Migration 0001 was not modified. Its source SHA256 remains
`2924d25751840d0b269eea9fbfd4571f6b53c70663b417758d6353de0664db61`.

Incident row integrity before migration, after migration and after all drills:
`2df093db77be7cd85bed2737d26fcf3070ebb9f8f58d97785a6264884a5ae027`, count **1** each time.
This SHA256 streams canonical-session-UTC row JSON ordered by ID, separated by newlines;
no incident text or credentials are included in evidence files.

Unrelated relation metadata SHA256 before/after:
`c0c444c24d7439279a654cd02a621a1dbefbb79c3a7ddff3279612e2b5c9d672`.
No resets, deletes, truncation, destructive migrations or unrelated writes were executed.

## Executed tests and live behavior

| Validation | Actual result |
|---|---|
| Opt-in PostgreSQL tests | **5 passed**, 90 deselected, 24.40 seconds; synthetic rows rolled back |
| Offline regression after harness additions | **90 passed**, 5 deselected, 4.00 seconds |
| Lint / format / compilation | PASS for backend and validation scripts; no new runtime dependencies |
| Approved artifact | Pinned Apache_2k.log, 171239 bytes, SHA256 verified before ingestion; no other public dataset ingested |
| Source reconciliation | **2000 processed = 2000 inserted + 0 duplicates + 0 rejected** on first completed audit run |
| Replay | **2000 processed = 0 inserted + 2000 duplicates + 0 rejected**; stored event count remains 2000 |
| Real process interruption | Worker terminated after committed checkpoint 250; another process resumes the same run after natural lease expiry, reaches 2000; no counter inflation or missing events |
| Concurrent claim | Independent worker process blocked while the first worker owned its run; no extra run created |
| Stale-owner fencing | Separate worker paused at checkpoint 250 until natural lease expiry; successor claimed the run; stale commit AND stale failure update both rejected; successor completed |
| Checkpoint / lease handling | No persistent lease timestamps or DB clock were edited; both live takeovers waited for real expiry |
| Log API | Full source-line pagination returns exactly 2000 unique IDs; level/message/local-time filters, detail, manifest, run/error reads work; owner token omitted; timezone-bearing filter rejected |
| Incident and health regression | Live/readiness and incident list/detail passed; incident POST behavior also covered by rollback-only integration tests |
| Actual backend restart | Two separate uvicorn processes each returned all 2000 identical event IDs and readiness 200; original incident count remains 1 |
| Final audit state | **3 completed; 0 partial; 0 failed; 0 running/interrupted** |

The three durable audit runs are the recovered first ingestion, duplicate replay, and
recovered stale-owner fencing run. Two temporary interruption states were intentionally
created and recovered. No additional synthetic rows survived the integration tests.

## Measured resources

Measurements are observed values for this small sample and validation sequence, not
estimates or guarantees for larger datasets. MiB means 1,048,576 bytes.

| Metric | Bytes | MiB | Target |
|---|---:|---:|---|
| Log relations before 0002 | 0 | 0 | Baseline |
| Empty log relations immediately after migration | 131072 | 0.125 | Includes indexes/TOAST allocation |
| Before public ingestion, after rolled-back integration tests | 253952 | 0.2422 | Includes physical allocation from test transactions |
| Final total log relations | **1277952** | **1.21875** | **PASS: <10 MiB** |
| Increment during public ingestion/replay/drills | **1024000** | **0.97656** | Subset of total increment |
| Maximum measured worker memory increment | **6029312** | **5.75** | **PASS: <100 MiB** |
| Maximum whole worker process peak working set | **100564992** | **95.90625** | Additional context, includes Python/import baseline |

Storage sums PostgreSQL pg_total_relation_size for the five log tables, including indexes
and TOAST. Final measurement also includes migration overhead, test allocation, audit
history and drill effects; unrelated tables and existing incidents are excluded.

Memory uses Windows GetProcessMemoryInfo: each ingestion worker's high-water working set
minus its working set immediately before ingestion. Five samples cover killed, expired,
resumed, replay and successor workers. Baselines include imports/connection verification.
This measures resident working set, not private commit size or total machine RAM. It
does not include the separate controller/API processes. Full sample values are preserved
in worker_memory.json. No resource benchmark numbers are inferred from offline tests.

## Evidence and reproduction

Sanitized evidence is under [phase2b-live-evidence/](phase2b-live-evidence/): preflight,
postmigration, final, crash_checkpoint, first_ingestion_recovered, replay, fencing,
api_checks, process_restart, worker_memory and measurements JSON. The migration baseline
is `docs/migrations/0001_incidents--0002_logs.inspection.json`.

Validation utilities added:

- `scripts/validate_phase2b_live.py`: known-project development guard and read-only
  preflight/postflight integrity receipts.
- `scripts/phase2b_live_drill.py`: authorized one-time ingestion/fault/resource drill;
  refuses an unexpected existing audit history. Do not rerun on this populated database.
- `scripts/phase2b_restart_probe.py`: read-only process restart and event-ID verification.

Live tests used:

```powershell
$env:INCIDENTIQ_RUN_DB_TESTS='1'
$env:INCIDENTIQ_RUN_LOG_DB_TESTS='1'
.\.venv\Scripts\python.exe -m pytest apps/api/tests -m database -q --tb=no -p no:cacheprovider --basetemp .pytest-db-live-20261021-a
Remove-Item Env:INCIDENTIQ_RUN_DB_TESTS
Remove-Item Env:INCIDENTIQ_RUN_LOG_DB_TESTS
```

For a future test run choose a fresh temporary directory. Do not reapply the migration,
reset the database, or rerun the one-time ingestion drill merely to reproduce test output.
Raw download and control markers stay in ignored .cache/loghub; api.env remains ignored.
No credentials, ownership tokens, incident text or raw logs are included in repository
evidence. No commit was made as part of this validation task.

## Failures and limits

The first connection attempt was blocked by sandbox network permissions; the approved
outside-sandbox probe succeeded. The first pytest invocation produced five setup errors
with Windows temporary/cache-path warnings; retrying with a fresh workspace basetemp and
cache disabled passed all five tests. These were not migration or integrity failures.
The Starlette/HTTPX deprecation warning remains. No business-code fixes were required.

SSL encryption with sslmode=require is verified; full CA/hostname verification is not
claimed. Owner-role access and unauthenticated loopback APIs remain development limits.
Research/academic Loghub license constraints still apply. Resource results cover this
artifact and these runs only. Frontend source was unchanged; this session verified backend
incident contracts and health, not a new browser UI exercise. Previous frontend lint,
TypeScript, 12 tests, build and proxy smoke evidence remains in the offline report.

Phase 2B is complete for the authorized development validation. Stop here; any Phase 2C,
deployment, authentication, additional datasets or AI feature work needs a new instruction.
