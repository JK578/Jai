# ADR 0005: Incident domain and ephemeral storage

Status: Accepted

Decision: Use frozen Python dataclasses with UUID4 identities, severity/status enums and
UTC timestamps. New incidents are open and created_at equals updated_at; no update
operation exists yet. Pydantic HTTP models trim strings, forbid extra fields and validate
lengths/enums. Domain invariants also protect callers outside HTTP.

IncidentService uses a structural IncidentRepository protocol. The composition root injects
a lock-protected, per-app in-memory adapter. Lists are snapshots ordered newest first with
UUID as tie-breaker. No global incident collection or generic persistence framework exists.

Next.js same-origin route handlers forward only incident routes to BACKEND_URL. The browser
cannot choose the upstream origin. Five-second upstream timeouts and sanitized 502 errors
bound failures. Client components provide forms, lists and selected details; health
connectivity remains server-side. Node's built-in test runner and the existing TypeScript
compiler run tests serially with dev-only React Testing Library/DOM and jsdom.

Tradeoffs: Data disappears on backend process restart/reload/exit. Use one API worker;
multiple workers hold different data. Storage is unbounded and intended for small local
demo datasets. No authentication, tenancy, persistence, pagination, editing, deletion or
status transitions exist. Phase 2 replaces the adapter with Supabase PostgreSQL/SQLAlchemy
and adds migrations/access enforcement before real user data. No Python dependencies
were changed or downgraded; no cloud or AI implementation was added.
