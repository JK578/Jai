# IncidentIQ

AI-powered incident investigation platform for learning and portfolio development.
For a fresh Windows environment, see [the quick start](docs/quickstart.md):
`py -3.15 scripts/dev.py setup`, then `py -3.15 scripts/dev.py run` for the configured
full workspace or add `--basic` for a credential-free incident-only demo.
Phase 2A persists incident creation, listing and details in Supabase PostgreSQL through
SQLAlchemy. Alembic owns schema changes; startup never creates tables or runs migrations.
With DATABASE_URL set, auto storage uses PostgreSQL. Explicit memory mode remains for
offline demos/tests. Phase 3 adds an offline-tested model gateway with mock and OpenAI
adapters and an explicit local CLI. Phase 4 adds live-validated persistent hybrid log
retrieval and cited CLI search. Phase 5 adds a checkpointed LangGraph investigation CLI
with human review before local report publication. Local authentication, tenant-scoped
database access, the investigation UI and read-only MCP are now implemented.

- [Current local setup, completion evidence and remaining verification limits](docs/local-completion.md)
- [Phase 6 MCP setup and tool boundaries](docs/phase6-mcp.md)
- [Local standalone frontend packaging and rollback](docs/phase7-frontend-release.md)
- [Isolated Python environments and rollback](docs/phase7-python-release.md)
- [Phase 8 investigation quality evaluation](docs/phase8-quality.md)

- [Phase 3 model gateway and configuration](docs/phase3-model-gateway.md)
- [Phase 4 retrieval completion and CLI usage](docs/phase4-completion.md)
- [Phase 5 investigation workflow, setup and verification](docs/phase5-investigations.md)

- [Windows setup and commands](docs/development.md)
- [Architecture diagrams](docs/architecture.md)
- [Roadmap and acceptance criteria](docs/roadmap.md)
- [Architecture decisions](docs/adr/)
- [Verification record](docs/verification.md)
- [Phase 1 implementation review](docs/phase1-review.md)
- [Phase 1B completion and file inventory](docs/phase1b-completion.md)
- [Incident API contracts](docs/api.md)
- [Persistent storage completion and migration evidence](docs/phase2a-storage.md)
- [Phase 2B log ingestion and migration approval runbook](docs/phase2b-ingestion.md)

## Repository

```text
.github/workflows/ci.yml
apps/
  api/
    .env.example
    pyproject.toml
    requirements-dev.lock.txt
    src/incidentiq/{__init__,config,main}.py
    src/incidentiq/domain/{__init__,incidents}.py
    src/incidentiq/application/{__init__,incidents}.py
    src/incidentiq/infrastructure/{__init__,memory,database,models,postgres}.py
    src/incidentiq/api/{__init__,incidents}.py
    tests/test_health.py
    tests/test_incidents.py
    tests/{conftest,test_postgres,test_database_integration}.py
    alembic.ini
    migrations/env.py
    migrations/script.py.mako
    migrations/versions/0001_incidents.py
    migrations/versions/0002_logs.py
    src/incidentiq/{domain/logs,application/log_ingestion,application/log_source}.py
    src/incidentiq/infrastructure/{log_models,log_repository,log_source}.py
    src/incidentiq/api/logs.py
    src/incidentiq/datasets/{apache_2k.json,LOGHUB-LICENSE.txt}
    tests/{log_fake,test_logs,test_log_repository,test_logs_database,test_migration_ranges}.py
    tests/fixtures/
  web/
    .env.example
    package.json
    package-lock.json
    next.config.ts
    next-env.d.ts
    tsconfig.json
    eslint.config.mjs
    postcss.config.mjs
    src/app/{layout.tsx,page.tsx,globals.css}
    src/lib/backend.ts
    src/lib/{incidents,incident-proxy}.ts
    src/components/{create-incident-form,incident-workspace}.tsx
    src/app/api/v1/incidents/route.ts
    src/app/api/v1/incidents/[incident_id]/route.ts
    tsconfig.test.json
    tests/{setup.ts,fixtures.ts,incidents.test.ts,workspace.test.tsx}
    tests/backend.test.ts
docs/
  architecture.md
  development.md
  roadmap.md
  verification.md
  phase1-review.md
  phase1b-completion.md
  api.md
  phase2a-verification.md
  phase2a-storage.md
  migrations/{0001_incidents.sql,inspection.json,applied.json}
  adr/0001-modular-monolith.md
  adr/0002-runtime-and-dependencies.md
  adr/0003-health-and-server-connectivity.md
  adr/0004-future-platform-boundaries.md
  adr/0005-incident-domain-and-ephemeral-storage.md
  adr/0006-postgres-persistence-and-reviewed-migrations.md
scripts/smoke.py
scripts/{verify_database,manage_database}.py
scripts/{ingest_logs,migration_catalog}.py
.gitignore
README.md
```

Use Python 3.15, Node 24 and npm 11. Run one backend worker and one frontend process.
Never commit `api.env`, `.env`, `.env.local`, API keys or database credentials. `.env.example`
contains only non-secret defaults. CI uses memory mode and needs no cloud credentials. This is a foundation,
not a production-ready enterprise application.

Phase 2B is live-validated in the approved Supabase development database. Migration 0002
is applied; the pinned sample has 2,000 persisted events, with duplicate-safe replay,
real worker interruption/resume, fencing and backend restart verified. Measured log
storage is 1.22 MiB and maximum worker memory increase is 5.75 MiB. See the
[live validation report](docs/phase2b-live-validation.md). Do not reapply the migration
or rerun the one-time drill. Logs are now available in the authenticated workspace;
no ingestion worker runs on API startup.
