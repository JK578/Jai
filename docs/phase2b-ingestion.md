# Phase 2B ingestion: implementation and approval runbook

Update 2026-10-21: approved migration 0002 and live validation are complete. See
[current evidence](phase2b-live-validation.md). The first-application steps below are
historical; do not reapply 0002 or rerun the one-time ingestion drill on this database.

2026-10-20. **Migration 0002 is generated, not applied. No live database inspection,
changes or ingestion were performed in this milestone.** Offline results are recorded
in [the completion report](phase2b-completion.md).

## Public source

The packaged manifest pins `Apache/Apache_2k.log` from
[LOGPAI Loghub](https://github.com/logpai/loghub) at commit
`dd61d0952749ee7963bde24220d1be5ede023033`. Its public bytes were read to establish the
checksum and size; the corpus was not committed or ingested into Supabase.

| Property | Verified value |
|---|---|
| Bytes / lines | 171239 / 2000 |
| SHA256 | c7efa3eb686e3a96bd2f8f4457b2a7887e9cf2f3649327f1b4e87af841363ce8 |
| Parser | apache-error-v1; strict UTF-8, bounded physical lines |
| Time | Original text and naive local time; UTC NULL, unknown zone |
| Terms | [Research/academic license](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE), not Apache License 2.0 |
| Provenance | [Apache README](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/Apache/README.md) links log-sharing.dreamhosters.com; original collection bundle not established |

The downloader accepts only the pinned raw GitHub URL, rejects redirects, uses TLS defaults
and timeouts, and validates bytes/lines/SHA256 before publishing the cache file. Copies
include the upstream license notice. `.cache/loghub/` is ignored. Ingestion reads a private
verified disk snapshot to prevent cache replacement after verification. Committed fixtures
are invented text. No anomaly labels, incident correlation or timezone are inferred.

## Proposed database schema

All five new tables are in `incidentiq`. Foreign keys use ON DELETE RESTRICT.

| Table | Fields and constraints |
|---|---|
| log_datasets | UUID PK, unique slug, provenance/license manifest JSON text |
| log_files | UUID PK, dataset FK, unique(dataset_id,sha256), byte/line bounds, parser version, commit/path |
| log_ingestion_runs | UUID PK, file FK, state/counts/checkpoint, start/finish/heartbeat/lease, private owner token, safe failure code; counts/state/lease checks |
| log_events | UUID5 PK, file FK, unique(file_id,source_line), raw text/digest, source timestamp/level, naive time, NULL UTC, normalized level, UTC ingestion time; size/level/line checks |
| log_ingestion_errors | PK(run_id,source_line), run FK, unique(run_id,sample_number), ordinal 1..100, fixed error code/digest; no raw excerpts |

Indexes cover file/time/line, file/level/line and run start/id. A unique partial index on
running state permits one active worker globally. Source-line uniqueness supports stable
event pages. No vector, FTS or ML infrastructure is introduced.

Reviewed [0002 SQL](migrations/0002_logs.sql), exact range `0001_incidents:0002_logs`,
canonical LF-text SHA256:
`d3f59a42af151a26995248cd2c1604ba8bcaa5ef30339fbf528dd75432618094`.
Use the tool's printed hash, since Get-FileHash can differ on a CRLF checkout.
The SQL creates five tables and indexes, enables RLS/revokes grants, and updates only
the dedicated Alembic version row. No DROP, ALTER incidents or unrelated DDL appears.
Downgrade removes only these five tables in reverse dependency order, destroying log data;
it is not exposed by the guard or approved here. Prefer a reviewed forward fix.

0001 source and its SQL receipt are unchanged. The guard uses Alembic ancestry and
per-revision snapshots; status validates the actual current revision, not repository head.
Preflight validates table/type/nullability/key/index/constraint identities and grants,
binds a database identity hash, and fingerprints existing table data/structure plus
unrelated relation metadata. The upgrade rechecks the exact baseline under transaction
advisory and SHARE locks and verifies protected data/metadata before commit. Reflected
constraint definitions are included in the baseline/postflight fingerprint; operator SQL
review is still required. Future additive revisions add reviewed snapshots; existing-table
DDL changes require a separate guard policy. Receipts contain hashes/metadata, never rows
or connection URLs. Stop API writes while taking and applying the baseline.

## Bounds and recovery

- Default batch 250, allowed 10..500, estimated normalized bytes <=512 KiB.
- File <=2 MiB / 2000 lines; line <=16 KiB. No pandas or whole-file read.
- Up to 100 error digests/codes per run, with full rejection counters. At 50 audit runs,
  stop for retention review; no automatic deletion. DB >400 MiB fails preflight.
- Checkpoint, events, diagnostics, counts and renewed lease commit atomically.
- Same file/line gives the same UUID; repeated equal messages on different lines survive.
- Re-ingestion creates an audit run and counts duplicates without inserting more events.
- Run row locks, owner tokens and a 60-second DB-clock lease fence every write.
  Claims serialize with a transaction-scoped advisory lock and the unique running index.
- An expired running run reads as interrupted. Explicit resume reclaims the same run with
  a new token and skips committed lines. Failed runs may resume. Stale owners cannot
  insert, finish or fail the successor. Digest conflicts roll back the batch.
- Classified transient errors allow two retries. Unknown commit outcomes reconcile the
  checkpoint first. If reconciliation cannot connect, stop safely and resume later.

Storage <10 MiB and incremental worker RSS <100 MiB remain **NOT VERIFIED live**.
PostgreSQL page/index overhead and allocation/bloat require actual measurement. The
400 MiB preflight leaves headroom within the project's assumed 500 MiB budget; confirm
the actual subscription quota before approval. The API pool max 2 plus CLI NullPool max 1
can total three connections. Stop the web dev server during measurement if RAM is tight.
No new packages or Python downgrade are needed. Current owner-role and unauthenticated
API remain local-development limitations; access control is a separate milestone.

## Safe apply steps: ONLY AFTER APPROVAL

Stop API writes/workers. Confirm ignored `apps/api/api.env` targets the intended
development database without displaying its value. Use the existing venv from repo root.
Do not stamp, reset or bypass drift failures.

```powershell
Set-Location 'C:\Users\Jayakrishna\Documents\Projects\IncidentIQ'
.\.venv\Scripts\python.exe -m scripts.manage_database plan --from-revision 0001_incidents --to-revision 0002_logs
Get-Content docs/migrations/0002_logs.sql
.\.venv\Scripts\python.exe -m scripts.manage_database status --from-revision 0001_incidents --to-revision 0002_logs
.\.venv\Scripts\python.exe -m scripts.manage_database inspect --from-revision 0001_incidents --to-revision 0002_logs
Get-Content docs/migrations/0001_incidents--0002_logs.inspection.json
# Stop on unexpected objects, drift, or baseline changes.
.\.venv\Scripts\python.exe -m scripts.manage_database upgrade --from-revision 0001_incidents --to-revision 0002_logs --reviewed-sha256 d3f59a42af151a26995248cd2c1604ba8bcaa5ef30339fbf528dd75432618094
.\.venv\Scripts\python.exe -m scripts.manage_database status --from-revision 0001_incidents --to-revision 0002_logs
```

Ingestion needs explicit approval too. After approved migration, run rollback-only tests
with no active ingestion worker. They write invented rows inside a rolled-back outer
transaction; they never migrate/create/reset tables. Then, if authorized, fetch/ingest:

```powershell
$env:INCIDENTIQ_RUN_DB_TESTS = '1'
$env:INCIDENTIQ_RUN_LOG_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest apps/api/tests -m database -q
Remove-Item Env:INCIDENTIQ_RUN_DB_TESTS
Remove-Item Env:INCIDENTIQ_RUN_LOG_DB_TESTS
.\.venv\Scripts\python.exe -m scripts.ingest_logs fetch
.\.venv\Scripts\python.exe -m scripts.ingest_logs ingest --source .cache/loghub/c7efa3eb686e3a96bd2f8f4457b2a7887e9cf2f3649327f1b4e87af841363ce8.log --allow-development-ingestion
# Resume with the same source plus --resume <API-reported-run-uuid> after failure/expiry.
```

Record incident counts/IDs before/after; verify unchanged. Measure sum of
pg_total_relation_size for the five log tables (including indexes/TOAST) before/after,
plus Windows worker peak working set versus idle baseline. Re-ingest and verify no added
events; counters must reconcile all 2000 physical lines. Restart API and verify persistence.
Perform an approved process-kill/resume drill and two-process ownership test. Verify read
filters/pages and existing frontend. Do not claim all lines parse until the real corpus
is actually ingested. Store only non-secret evidence.
