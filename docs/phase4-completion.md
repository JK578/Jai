# Phase 4 completed — 2026-11-06

Hybrid retrieval is implemented and live-validated for the approved 2,000-event Apache
development corpus. PostgreSQL stores 2,000 event documents with 512-dimensional
`text-embedding-3-small` vectors. Keyword/full-text and vector/cosine rankings are fused
with reciprocal rank fusion. Every hit carries the original event/file IDs, source line,
source path, pinned commit and file checksum. Inference remains an explicit backend CLI;
there is no retrieval UI or public paid-inference endpoint in this milestone.

## Completed acceptance checks

| Check | Executed result |
|---|---|
| Budgeted corpus indexing | 2,000 documents published atomically; 886 distinct messages embedded once each; every original event identity retained |
| Replay/idempotency | Existing matching snapshot detected; zero new embeddings, no replacement writes, identical full vector/content fingerprint |
| Resume | Digest-only vector cache written atomically after each batch; offline test simulates second-batch failure and resumes only missing inputs; live cache contains the completed corpus |
| Real search evaluation | Eight source-labelled development queries compared across actual PostgreSQL keyword/vector/hybrid branches; all returned citations matched source evidence |
| Deletion | Live rollback-only integration test removes a synthetic file's indexed documents while retaining its source events; actual public corpus remains indexed |
| Persistence | Two fresh Python CLI processes read all 2,000 vectors with identical full-index fingerprints; evaluation also ran from a fresh process |
| Source integrity | All six original tables' data/structure hashes and unrelated relation metadata match the reviewed pre-migration baseline |
| Regression | 170 offline tests passed; all 6 opt-in PostgreSQL tests passed (36.51 seconds); Ruff lint/format for 65 files and pip consistency passed |
| Backend health | PostgreSQL readiness returned ready/200 |

The persistence check starts fresh application processes/connections. It does not restart
the hosted PostgreSQL service. Resume was fault-tested offline; no live process was killed
during paid embedding. Existing Starlette/HTTPX TestClient deprecation warning remains.

## Search quality baseline

The relevance criteria in [phase4-queries.json](phase4-queries.json) were specified from
source-message categories before running queries. They cover exact state numbers, worker
initialization, child initialization, scoreboard slots and three paraphrases. Regex criteria
resolve all matching source lines, preserving repeated legitimate events. This is an
eight-query development baseline, not an independently annotated or held-out benchmark.
No query labels or ranking parameters were tuned after observing these results.

| Method | Queries with relevant top-5 evidence | MRR@5 | nDCG@5 |
|---|---:|---:|---:|
| PostgreSQL keyword | 4/8 (50%) | 0.5000 | 0.5000 |
| Exact vector | 7/8 (87.5%) | 0.8750 | 0.8567 |
| Hybrid RRF | 7/8 (87.5%) | 0.8750 | 0.8567 |

The query `connector worker environment failed` missed relevant evidence in all three
methods. Hybrid matched vector performance here; this small set does not demonstrate that
fusion improves on vector search. Recall@5 is about 0.1848 for vector/hybrid because some
queries have hundreds of relevant repeated source lines and only five results are returned.
Maximum observed database-search call time was 1,158.55 ms, including connection/network
work; this is a small-run observation, not a production latency guarantee.

See [full real-corpus evaluation](phase4-live-evaluation.json). The earlier curated-vector
[synthetic evaluation](phase4-evaluation.json) remains a mechanics test, not model evidence.

## Measured cost and resources

- Corpus embeddings: 12,606 provider-reported input tokens; query embeddings: 41 tokens.
  At the checked $0.02 per million token rate, combined estimated provider cost is
  **$0.00025294**. Actual billing, taxes and remaining account balance were not queried.
  Model pricing source: [official model documentation](https://developers.openai.com/api/docs/models/text-embedding-3-small).
- The indexing invocation had a conservative $0.10 budget; evaluation had a $0.02 budget.
  Accounting reserves one micro-USD per input byte, refunds successful reported token
  usage differences and retains reservations on errors. These are local invocation
  limits, not a durable account-wide limit. No automatic retries occur.
- Final retrieval relations: **6,373,376 bytes (6.078125 MiB)**, including indexes and
  allocation from rollback tests; validation target <10 MiB passed.
- Indexing worker peak working set: **180,551,680 bytes (172.1875 MiB)**; peak minus its
  pre-indexing working set: **82,853,888 bytes (79.015625 MiB)**. Incremental <100 MiB
  target passed. Native Windows process counters include Python/import baseline in the
  whole-process peak and exclude the separate API/web processes. These observations
  cover this corpus, not future corpus sizes.

## Commands

Run from the repository root with the configured ignored `apps/api/api.env`:

```powershell
# Index or resume. Matching live snapshot skips paid embedding and database replacement.
.\.venv\Scripts\python.exe -m scripts.retrieval_cli index --budget-microusd 100000

# Read-only count, storage and full index fingerprint; no API call.
.\.venv\Scripts\python.exe -m scripts.retrieval_cli status

# One budgeted query; prints source citations and matching text to the local terminal.
.\.venv\Scripts\python.exe -m scripts.retrieval_cli search --query 'successful worker environment initialization' --budget-microusd 20000
```

The CLI is restricted to the pinned approved file and development database configuration.
It requires revision 0003 and does not migrate, ingest more datasets or delete original logs.
Cache files under ignored `.cache/retrieval/` contain message digests/vectors, never raw
messages or credentials. Deleting that cache is unnecessary; it enables resume before
publication and is not the source of database search persistence.

## Evidence

- [Indexing and worker measurement](phase4-indexing.json)
- [Replay without API calls](phase4-replay.json)
- [Fresh process A](phase4-restart-a.json), [fresh process B](phase4-restart-b.json)
- [Final integrity/resource verification](phase4-final-verification.json)
- [Reviewed migration and application history](phase4-migration-review.md)

The next roadmap milestone is Phase 5, the investigation workflow. Authentication,
tenant authorization, durable shared spending controls, broader retrieval evaluation
and a retrieval UI remain separate future work.
