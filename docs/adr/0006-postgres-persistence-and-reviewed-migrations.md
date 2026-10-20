# ADR 0006: PostgreSQL persistence and reviewed migrations

Status: Accepted. Supersedes ADR 0005's temporary storage choice for configured deployments.

Decision: Keep the domain, repository protocol and incident HTTP contracts. Map immutable
domain objects to SQLAlchemy rows through a synchronous PostgreSQL adapter. Each operation
owns a short-lived Session; writes use begin/commit/rollback and reads close/rollback on
exit. Sessions are never shared between FastAPI worker threads. Dispose the engine at shutdown.

Use auto/memory/postgres selection. Auto chooses PostgreSQL when DATABASE_URL exists;
explicit postgres requires it. Missing schema/unavailable database never falls back to
memory. Tests pass isolated Settings/repositories and default CI does not need credentials.
DATABASE_URL is a hidden/excluded Pydantic SecretStr and is loaded only from ignored api.env
or process environment. SSL require is the minimum; preserve verify-ca/verify-full when set.
Use psycopg 3.3.6 binary wheels, SQLAlchemy 2.1.5 and Alembic 1.20.0 on Python 3.15.

Limit the per-process pool to two connections, zero overflow; enable pre-ping and a 300-second
recycle. Bound connect/pool waits to five/two seconds and SQL statements to three seconds.
Disable prepared statements for pooler compatibility. Fixed domain/application storage errors
become safe 503/409 HTTP responses without logging raw SQL, parameters or exception messages.
Synchronous readiness runs in FastAPI's thread pool, checks the table (including missing
schema), and reports not_ready/503 on database failure. Liveness does not query the database.

Use a private incidentiq schema with one incidents table. Avoid PostgreSQL custom enum types
by using constrained strings, easing future migrations. UUIDs and UTC timestamps stay
application-assigned, preserving existing contracts. The ordering index covers created_at/id.
RLS is enabled without browser policies; revoke PUBLIC/anon/authenticated schema/table access.
The backend's configured owner role can access it; a least-privilege role and user/tenant
authorization are next-phase work. Do not expose this unauthenticated API publicly.

Track migrations in public.incidentiq_alembic_version, avoiding a pre-migration schema-creation
bootstrap and collision with generic alembic_version tables. Restrict that new table too.
The guarded initial migration inspects absence of conflicting objects, fingerprints unrelated
metadata, compares reviewed offline SQL and hash, takes a transaction advisory lock, and
checks unrelated metadata before commit. Unexpected differences stop/rollback; there is no
reset, drop, create_all, migration on startup, or unrestricted autogeneration over Supabase.
The applied initial revision is immutable. Future revisions require another explicit review.

Verification uses rollback-only opt-in PostgreSQL tests plus a separate real-process smoke
test that retains one newly created development evidence incident across restart. It never
deletes pre-existing rows. Frontend contracts remain compatible; storage labeling derives
from an additive, non-secret readiness storage field. Certificate/hostname verification is
not established by sslmode=require; configure verify-full before production deployment.
