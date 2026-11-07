# Local access-control review

Prepared and reviewed 2026-11-06 under the user's instruction to complete the remaining
milestones for local-only deployment. Migration 0004 adds one resource ownership table,
a NOLOGIN restricted group role, explicit grants and tenant-scoped RLS policies on the
existing application tables. It does not alter source columns, drop tables or delete data.

Reviewed SQL: [0004_access.sql](migrations/0004_access.sql).
Canonical SQL SHA256: `1c88b90f983673d531991351d41d64748753a0970e44e4645abb990c4a43d3e4`.
The [revision snapshot](migrations/0004_access.schema.json) includes canonical policy
definitions captured during a rolled-back preview. The migration guard now verifies
those exact definitions and the group's no-login/no-administrative flags.

Executed rollback-only tests switched to the real restricted group role. The assigned
tenant saw 2,000 log/vector rows and its incident; another tenant saw none. The second
tenant could create its own incident, while DELETE, UPDATE and CREATE TABLE attempts
were rejected with PostgreSQL 42501. Preview-only owner role-assumption membership and
all invented rows/mappings were rolled back. Source data/structure and unrelated relation
metadata hashes matched before/after. No persistent schema change occurred during preview.

HTTP token authentication, expiry/revocation, tenant memory isolation and permission
denial tests passed. Migration 0004 was then applied through the reviewed guard.
Runtime activation uses a separate non-owner login, TLS hostname verification with the
Supabase CA, transaction-local tenant settings and ignored local token hashes. Existing
owner credentials remain for explicit trusted operator migrations/ingestion CLIs only.

See [provisioning](access-provisioning.json), [final integrity](access-integrity.json) and
[the release drill](local-release-validation.json). Source/retrieval fingerprints are unchanged.
