# Phase 4: hybrid retrieval

Status (2026-11-06): Phase 4 is complete for the approved development corpus. All 2,000
events are persistently indexed, real-corpus search evaluation and replay/persistence/
resource checks passed, and 170 offline plus 6 PostgreSQL tests passed.
See the [current completion report](phase4-completion.md). The sections below describe
the original reference slice and its historical implementation plan.
The reference slice provides the retrieval contracts, offline reference index, bounded OpenAI
embedding adapter and reproducible synthetic evaluation. It does not index the live
2,000-event corpus or change the existing database schema.

## Implemented behavior

`RetrievalService` stages batches of at most 16 evidence records and publishes a file
snapshot only after every embedding succeeds. Rebuilding replaces that file's snapshot
instead of accumulating duplicates; failures preserve the previous snapshot. File deletion
removes both the keyword and vector representations in the reference index. Searches
operate on immutable snapshots: a query already in flight can finish against its snapshot.

Evidence preserves event UUID, file UUID, source line, source path, commit and file SHA256.
These fields are returned intact with the matching text. No LLM generates citations.
Records are limited to 8,000 UTF-8 bytes, matching the conservative embedding allowance;
longer log messages require a separately versioned chunking policy before live indexing.
Synthetic fixtures use a zero commit marker and their actual fixture file digest, not
fabricated upstream provenance.

The bounded reference index supports at most four files, each with up to 2,000 records
through the application service. Search combines BM25 keyword ranks and exact normalized
cosine similarity ranks. Each branch contributes up to 50 candidates; reciprocal rank
fusion uses k=60. Final ties break by event UUID for repeatable output. Queries are limited
to 800 UTF-8 bytes and results to 20. Non-positive cosine candidates are omitted. Ranking
scores describe relevance, not factual confidence or anomaly probability.

`OpenAIEmbeddingProvider` uses `text-embedding-3-small` at 512 dimensions, via the fixed
HTTPS embeddings endpoint. The official [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
documents the dimensions parameter and embedding use. The adapter checks response model,
count, indices, dimensions, finite nonzero vectors and token usage. It restores input order
even if provider response items arrive out of order. No embedding call runs at API startup.

Its budget defaults to 20,000 micro-USD ($0.02), with a maximum of $0.10 per instance.
Before each call it reserves one micro-USD per input UTF-8 byte; successful reported token
usage refunds the difference, failures retain the reservation. This conservative local
accounting is not a durable account-wide cap. Requests have a 20-second HTTPX inactivity
timeout and an elapsed-time check between chunks, not strict wall-clock cancellation.
Response size is capped at 512 KiB. No retries, redirects or environment proxies are enabled.
The adapter is tested with MockTransport; no live embedding requests were made.

## Reproduce the evaluation

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_retrieval
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_retrieval.py -q
```

The fixture contains three synthetic records, three labelled queries and deliberately
curated three-dimensional vectors. Keyword Recall@1/MRR is 0.333333; vector and hybrid
Recall@1/MRR are 1.0. This demonstrates ranking/fusion and citation/deletion mechanics
only. It does not establish the quality of OpenAI embeddings, superiority of fusion,
or retrieval accuracy on the real Apache corpus. See the [evaluation receipt](phase4-evaluation.json).

## Historical implementation plan (now completed)

1. Prepare an additive reviewed PostgreSQL/pgvector index migration and revision snapshot,
   preserving the existing incident/log schema and data. Inspect extension availability
   and storage headroom. Apply only after the migration's SQL and scope are reviewed.
2. Persist versioned event/chunk embeddings with model, dimensions and content digests;
   implement database-backed keyword/vector candidates, atomic publication and scoped
   index deletion. Original logs and ingestion history must remain intact.
3. Index the approved corpus through an explicit bounded CLI, with a small total budget
   and restart/replay behavior; keep paid embedding work outside unauthenticated HTTP.
4. Evaluate real retrieval against independently labelled queries, record keyword/vector/
   hybrid baselines, and verify PostgreSQL deletion, persistence, resource use and regression.

No retrieval HTTP route, log UI, migration or external inference was added in this slice.
The reference index is intentionally ephemeral; it is not the production persistence adapter.
