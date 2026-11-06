# ADR 0007: Pinned, bounded and resumable public log ingestion

Status: accepted and live-validated 2026-10-21. See [measured evidence](../phase2b-live-validation.md).

Use the Loghub Apache 2,000-line sample at the manifest's immutable commit and SHA256.
Its license is research/academic terms, not Apache License 2.0. Keep the upstream notice
with downloaded copies, cite Loghub and preserve its provenance links. The upstream
Apache README points to log-sharing.dreamhosters.com; the exact original collection
bundle is not established. Public availability does not establish production suitability.
Only invented fixtures are committed; raw downloads live in an ignored cache.

Normalize datasets, files, runs, events and sampled errors in the private incidentiq
schema. Store immutable file/parser identity, raw evidence and source-local time with
unknown UTC. No incident foreign key is inferred from unrelated historical public data.
Use UUID5(file, physical line), plus unique(file_id, source_line); message deduplication
would destroy real repeated occurrences. Preserve inserted events across audit runs.

Prefer a synchronous local CLI over HTTP jobs, task queues or extra services. Bound
source size to 2 MiB/2,000 lines, lines to 16 KiB, batches to 10..500 records (250 default)
and 512 KiB estimated normalized bytes. Retain at most 100 error digests/codes per run
and permit at most 50 audit runs before explicit retention review. No automatic deletion.
Preflight rejects a database over 400 MiB. Storage below 10 MiB and incremental worker
RSS below 100 MiB are acceptance targets requiring a later live measurement, not claims.

Commit events, diagnostics and checkpoint atomically. Serialize claims with a transaction
advisory lock and enforce one running row with a partial unique index. Fence every write
with row lock, random ownership token and DB-clock lease. Explicit resume is required for
expired workers; a stale token cannot finish/fail or insert. Transaction locks work through
transaction poolers; persistent session locks are avoided. At most two retries follow
classified transient failures, with checkpoint reconciliation after uncertain commits.

Keep revision 0001 immutable. Add five tables in 0002 with RLS/revoked grants and RESTRICT
foreign keys. Generate SQL for an explicit revision range and bind the reviewed hash to a
development database/schema/data baseline. The guard validates the actual current
revision's snapshot rather than assuming head or a single initial revision. Future
additive revisions add reviewed snapshots; existing-table changes need a separately
designed guard policy. No migration or ingestion runs during startup.

Tradeoffs: literal substring queries suit 2,000 records without FTS infrastructure;
source-line cursors suit future MCP search citations. Run history uses bounded offsets.
The current owner-role, unauthenticated local API remains a development limitation.
Access control stays a separate milestone before deployment. No new dependency or
Python version change is required; PostgreSQL semantics must still be verified after
the explicitly approved migration, not inferred from fake repository tests.
