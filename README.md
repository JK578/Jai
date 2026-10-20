# IncidentIQ

AI-powered incident investigation platform for learning and portfolio development.
Phase 2A persists incident creation, listing and details in Supabase PostgreSQL through
SQLAlchemy. Alembic owns schema changes; startup never creates tables or runs migrations.
With DATABASE_URL set, auto storage uses PostgreSQL. Explicit memory mode remains for
offline demos/tests. No LLM, MCP, RAG or LangGraph integration is implemented.

- [Windows setup and commands](docs/development.md)
- [Architecture diagrams](docs/architecture.md)
- [Roadmap and acceptance criteria](docs/roadmap.md)
- [Architecture decisions](docs/adr/)
- [Verification record](docs/verification.md)
- [Phase 1 implementation review](docs/phase1-review.md)
- [Phase 1B completion and file inventory](docs/phase1b-completion.md)
- [Incident API contracts](docs/api.md)
- [Persistent storage completion and migration evidence](docs/phase2a-storage.md)

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
.gitignore
README.md
```

Use Python 3.15, Node 24 and npm 11. Run one backend worker and one frontend process.
Never commit `api.env`, `.env`, `.env.local`, API keys or database credentials. `.env.example`
contains only non-secret defaults. CI uses memory mode and needs no cloud credentials. This is a foundation,
not a production-ready enterprise application.
