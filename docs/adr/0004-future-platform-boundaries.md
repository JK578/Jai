# ADR 0004: Defer cloud and AI integration

Status: Accepted for target architecture; implementation deferred

Decision: Use Supabase PostgreSQL/pgvector with SQLAlchemy, OpenAI behind a provider-independent
gateway, LangGraph orchestration and later MCP servers. Hybrid retrieval combines keyword
and vector evidence. Keep credentials and privileged operations on the backend.

Consequences: External services reduce local memory usage, but add network, cost, privacy,
and availability dependencies. Implement no placeholder inference, database connection,
MCP server or retrieval workflow in the foundation milestone. Structured local logs precede
cloud tracing. GitHub Actions validates each implemented slice.
