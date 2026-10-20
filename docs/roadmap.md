# Implementation roadmap

Each milestone ends with executed checks and a review before proceeding.

Phase 0, Phase 1A and Phase 1B are implemented. Phase 1B adds incident create/list/detail
contracts, domain/service/repository boundaries and a UI with validation/loading/empty/error
states. Storage is explicitly ephemeral. See [Phase 1B verification](phase1b-completion.md).
The earlier [Phase 1A review](phase1-review.md) is historical. Phase 2 requires approval;
verify its database/driver/migration combination on Windows Python 3.15 before integration.

| Milestone | Scope | Measurable acceptance criteria |
|---|---|---|
| Phase 0 | Repository, architecture, ADRs, native setup, CI | Fresh checkout has documented setup; dependency installs succeed on Python 3.15 and Node 24; lint, types, tests, build execute without secrets |
| Phase 1A (complete locally) | Health API and connectivity page | Live returns 200; ready returns 200 after startup and 503 when disabled; page distinguishes ready, not ready, unavailable; no external service credentials required |
| Phase 1B (complete locally) | Typed incident domain and in-memory API slice | Create/list/detail incident contracts documented; invalid input rejected; tests cover creation invariants; frontend renders loading/empty/error/success states; ephemeral storage explicitly labelled |
| Phase 2 | Supabase PostgreSQL, SQLAlchemy, migrations, access boundaries | Migration applies to isolated cloud project; persistence survives restart; scoped access tests pass; no privileged keys reach browser |
| Phase 3 | Provider-independent model gateway | Mock and OpenAI adapters pass same contract tests; timeouts, cost limits and sanitized failures verified; inference stays server-side |
| Phase 4 | Hybrid retrieval | Fixture corpus ingested reproducibly; keyword/vector fusion evaluated against labelled queries; citations identify original evidence; deletion removes indexed data |
| Phase 5 | LangGraph investigation workflow | Deterministic mocked graph tests pass; resumability and failure behavior demonstrated; human approval required for consequential tool actions |
| Phase 6 | MCP tools | Independent server contracts tested; authentication and allowed tool boundaries verified; unauthorized calls rejected |
| Phase 7 | Hardening and delivery | Tenant/access tests pass; evaluation baseline recorded; tracing redacts secrets; deployment and rollback exercised |

Do not install speculative AI/database dependencies before their milestone. Budget external
API usage, evaluate generated claims against evidence, and add cloud tracing when workflows exist.
