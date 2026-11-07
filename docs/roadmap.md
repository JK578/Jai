# Implementation roadmap

Each milestone ends with executed checks and a review before proceeding.

Phase 0, Phase 1A, Phase 1B and Phase 2A persistent storage are implemented and locally verified.
The initial guarded migration is applied; real backend restart preserves incidents and
frontend proxy compatibility is verified. See [Phase 2A evidence](phase2a-storage.md).
Earlier phase reports are historical. Approved Phase 2B scope is public log ingestion;
access control is a separate milestone. Phase 2B migration and controlled live validation
are complete. See [measured live evidence](phase2b-live-validation.md). Subsequent user-authorized
Phase 3 and Phase 4 work is also complete; see [Phase 4 results](phase4-completion.md).
Phase 5 is complete for the local backend/CLI workflow; see [its validation and limits](phase5-investigations.md).
Access control, browser integration, Phase 6 and local Phase 7 checks are implemented.
See [current evidence and verification limits](local-completion.md).
Visual/mobile QA was explicitly deferred by the user on 2026-11-07. GitHub backend and
frontend CI passed for `16355d4`; see [the run](https://github.com/JK578/Jai/actions/runs/42350402461).
Phase 8 now adds [investigation quality evaluation](phase8-quality.md).

| Milestone | Scope | Measurable acceptance criteria |
|---|---|---|
| Phase 0 | Repository, architecture, ADRs, native setup, CI | Fresh checkout has documented setup; dependency installs succeed on Python 3.15 and Node 24; lint, types, tests, build execute without secrets |
| Phase 1A (complete locally) | Health API and connectivity page | Live returns 200; ready returns 200 after startup and 503 when disabled; page distinguishes ready, not ready, unavailable; no external service credentials required |
| Phase 1B (complete locally) | Typed incident domain and in-memory API slice | Create/list/detail incident contracts documented; invalid input rejected; tests cover creation invariants; frontend renders loading/empty/error/success states; ephemeral storage explicitly labelled |
| Phase 2A (complete locally) | Supabase PostgreSQL, SQLAlchemy and reviewed Alembic migration | Additive migration applied; unrelated schema unchanged; repository/API tests and persistence after process restart pass; no secrets reach browser |
| Phase 2B (live complete) | Pinned log ingestion, five tables, revision-aware migrations, read APIs | 0002 applied; 0001 and incident integrity unchanged; 5 PostgreSQL tests and 90 offline tests pass; 2000 events, zero replay insertions, real crash/resume and fencing/restart pass; measured 1.22 MiB storage and 5.75 MiB incremental worker working set |
| Access control (complete locally) | Authentication, scoped access and least-privilege database role | Unauthorized API calls rejected; tenant isolation tests pass; backend role limited to required objects; production SSL trust policy validated before deployment |
| Phase 3 (implemented; live smoke passed) | Provider-independent model gateway | Mock and OpenAI adapters pass shared contract tests; timeout/error and process-local cost controls verified; one synthetic live request succeeded. See [report](phase3-model-gateway.md) |
| Phase 4 (live complete) | Hybrid retrieval | 2,000 documents indexed; replay makes no API calls; eight labelled real queries evaluated; citations, scoped deletion, fresh-process persistence and integrity verified; 6.08 MiB retrieval storage / 79.02 MiB incremental worker memory. See [completion](phase4-completion.md) |
| Phase 5 (complete for local backend/CLI) | LangGraph investigation workflow | 22 deterministic workflow tests; fresh-process checkpoints/resume, safe failures and idempotent approved publication verified. One live investigation validated and paused for human review; 192 offline and 6 PostgreSQL tests pass. See [completion](phase5-investigations.md) |
| Phase 6 (complete locally) | MCP tools | Independent server contracts tested; authentication and allowed tool boundaries verified; unauthorized calls rejected |
| Phase 7 (agreed local scope complete) | Hardening and delivery | Access/isolation, local packaging/rollback and remote CI passed; visual/mobile QA deferred by user; cross-version runtime upgrades outside verified scope |
| Phase 8 (evaluation tooling implemented) | Report quality metrics and bound review annotations | 14 synthetic scorer regressions; citation/finding/fact metrics; changed artifacts invalidate labels; saved-report templates stay private; no unlabelled live accuracy claim |

Do not install speculative AI/database dependencies before their milestone. Budget external
API usage, evaluate generated claims against evidence, and add cloud tracing when workflows exist.
