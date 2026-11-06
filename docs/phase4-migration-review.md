# Phase 4 PostgreSQL retrieval: ready for review

Completion update: Phase 4 is now live-validated, including real-corpus indexing and
evaluation. See [current completion report](phase4-completion.md); the review/application
history below is retained as evidence.

Latest update 2026-11-06: migration 0003 is now applied following explicit user approval.
The guarded upgrade verified the target schema and preserved protected data/metadata.
The rollback-only PostgreSQL retrieval integration test passed (1 test, 8.35 seconds),
covering publication, real FTS/cosine search, replay, citations and scoped index deletion.
Final read-only verification found revision `0003_retrieval`, 2,000 original log events,
zero persisted retrieval documents and vector 0.8.2 in `extensions`. Backend readiness
returned 200/ready. No paid embeddings were performed. See [application receipt](migrations/0003_retrieval.applied.json).
Earlier preparation and approval instructions below are historical; do not reapply 0003.

Update 2026-11-06: the user-approved vector extension prerequisite is now applied.
Version 0.8.2 is installed in `extensions`; protected data/structure and unrelated relation
metadata were verified unchanged before commit. The database remains at `0002_logs`;
migration 0003 is not applied. See [enablement receipt](migrations/0003_vector_enabled.json).
The preflight and preparation sections below preserve the earlier review context.

No embeddings were purchased or source log data changed. This report covers the
authorized preparation of the database migration and retrieval adapter.

## Observed development preflight

The read-only probe confirmed revision `0002_logs`, 2,000 events and zero messages
requiring chunking under the current 8,000-byte evidence limit. Database size was
12,449,459 bytes (about 11.87 MiB), with 406,980,941 bytes below the existing 400 MiB
application threshold. These are PostgreSQL database bytes, not a Supabase billing
quota or dashboard free-space reading.

pgvector 0.8.2 is available but **not installed**. Enablement must therefore be separate
from the additive IncidentIQ table migration. Supabase documents the extension under
the PostgreSQL name `vector`: [extension guide](https://supabase.com/docs/guides/database/extensions/pgvector).

The guarded source inspection passed: all six existing IncidentIQ tables match the
reviewed 0002 schema, including RLS/grants. Current protected data/structure fingerprints
and the current unrelated-metadata baseline were captured in
[the inspection receipt](migrations/0002_logs--0003_retrieval.inspection.json).
This receipt establishes today's baseline; it does not assert that all unrelated objects
are unchanged since the historical October validation.

## SQL for review

1. [Separate extension prerequisite](migrations/0003_vector_prerequisite.sql): require
   an existing `extensions` schema and absent vector extension, then enable exactly
   `vector` version 0.8.2 there. It does not relocate, upgrade or drop an installed extension.
   This creates extension-owned types/functions/operators, not IncidentIQ log records.
2. [Migration 0003](migrations/0003_retrieval.sql): require vector in `extensions`, add
   `incidentiq.retrieval_documents`, one file index, RLS/revoked Data API grants, and the
   Alembic version update. No existing tables are altered. Existing migrations remain
   immutable. Downgrade is disabled; there is no automatic destructive rollback.

Canonical SHA256 hashes (UTF-8 text with LF line endings):

```text
Extension prerequisite:
81164720ba88927d17bb2df2478747432692c6be5467d54c80ff27670787efa4

0002_logs -> 0003_retrieval:
8d53bf0f6725cbbf2a38d36d178207f7eae5839c1e78d0051d9dd0f59f3bea53
```

The [0003 revision snapshot](migrations/0003_retrieval.schema.json) includes all previous
table shapes unchanged and pins the vector extension's schema/version. The migration
guard now reflects both `vector(512)` and schema-qualified `extensions.vector(512)` and
checks the extension prerequisite during target verification. It still compares protected
data/structure and unrelated relation metadata before committing a table migration.

## Adapter behavior

`PostgresRetrievalIndex` implements the same application retrieval port as the memory
index, plus `load_file`. Each event becomes one document with its event/file UUIDs,
embedding model, 512 dimensions, content SHA256, content, vector and indexing timestamp.
This is one active model snapshot per file, not a multi-model history store.

Publication normalizes/validates vectors before SQL, serializes replace/delete by a
file-specific transaction advisory lock, checks storage headroom, locks the source file
and events, and verifies the full source file and citation metadata. It rejects incomplete
files or changed evidence. Deletes and bounded inserts then commit together. Any failed
insert rolls the entire replacement back; source logs and ingestion audit rows are never
deleted. Query results also validate indexed content against current source content and
its stored digest. Model/dimension mismatches fail explicitly.

Search uses a single materialized file-scoped SQL snapshot for both branches and source
citations: PostgreSQL `simple` full-text ranking (`ts_rank_cd` + `plainto_tsquery`) and exact
pgvector cosine ranking. It fuses up to 50 candidates per branch using the shared RRF
implementation, and returns at most 20 hits. Values and vector literals are bound parameters.
The PostgreSQL keyword branch uses FTS, not the memory adapter's BM25 formula; real-corpus
evaluation must compare the actual database rankings. No additional keyword/vector index
is proposed for this small corpus beyond the file filter index. See the official
[pgvector operator reference](https://github.com/pgvector/pgvector#vector-operators).

All sessions close/rollback reads and commit writes explicitly. Existing three-second
statement limits, two-second mutation lock limits and pooler-compatible transaction locks
apply. No background worker, startup schema change, paid inference endpoint or UI is added.

## After approval

Keep application writers stopped during schema changes. Recheck the development target,
extension state, SQL hashes and storage. Execute only the separately reviewed extension
prerequisite, in its transaction, then verify version/schema and existing data/metadata.
Reinspect the source baseline after that prerequisite and apply only the guarded 0003 range:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_database inspect --from-revision 0002_logs --to-revision 0003_retrieval
.\.venv\Scripts\python.exe -m scripts.manage_database upgrade --from-revision 0002_logs --to-revision 0003_retrieval --reviewed-sha256 8d53bf0f6725cbbf2a38d36d178207f7eae5839c1e78d0051d9dd0f59f3bea53
.\.venv\Scripts\python.exe -m scripts.manage_database status --from-revision 0002_logs --to-revision 0003_retrieval
```

Then run the new rollback-only integration test with explicit opt-in:

```powershell
$env:INCIDENTIQ_RUN_RETRIEVAL_DB_TESTS='1'
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_retrieval_database.py -q -p no:cacheprovider --basetemp .pytest-retrieval-live-FRESH_UNIQUE_SUFFIX
Remove-Item Env:INCIDENTIQ_RUN_RETRIEVAL_DB_TESTS
```

This test ingests synthetic rows inside an outer rollback, publishes/replays a synthetic
index, checks real FTS/pgvector citations and verifies index deletion leaves source events
intact. It never migrates or modifies pre-existing rows. Original log integration tests now
accept either reviewed revision 0002 or 0003. No database integration tests have been run
against the proposed retrieval table yet; SQL execution semantics, transaction timing and
actual resource growth remain pending live verification.

Only after those checks should the next slice add the budgeted indexing CLI, embed the
approved real corpus, and evaluate labelled real queries. None of those steps is claimed
complete by this review report.
