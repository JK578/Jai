# ADR 0004: Defer cloud and AI integration

Status: Accepted for target architecture; implementation deferred

Update 2026-11-06: Phase 3 implements the provider-independent text model gateway with
mock and OpenAI adapters, bounded process-local cost accounting and an explicit CLI.
See [Phase 3 report](../phase3-model-gateway.md). Retrieval, orchestration and MCP remain
deferred. The foundation-only restrictions below describe the original milestone.

Decision: Use Supabase PostgreSQL/pgvector with SQLAlchemy, OpenAI behind a provider-independent
gateway, LangGraph orchestration and later MCP servers. Hybrid retrieval combines keyword
and vector evidence. Keep credentials and privileged operations on the backend.

Consequences: External services reduce local memory usage, but add network, cost, privacy,
and availability dependencies. Implement no placeholder inference, database connection,
MCP server or retrieval workflow in the foundation milestone. Structured local logs precede
cloud tracing. GitHub Actions validates each implemented slice.
