# IncidentIQ

AI-powered incident investigation platform for learning and portfolio development.
Phase 1B implements incident creation, listing and details, plus the health/connectivity slice.
Storage is in memory: incidents disappear on backend restart/reload. Use one backend worker.
No database, LLM, MCP, RAG, or LangGraph integration is installed or implemented.

- [Windows setup and commands](docs/development.md)
- [Architecture diagrams](docs/architecture.md)
- [Roadmap and acceptance criteria](docs/roadmap.md)
- [Architecture decisions](docs/adr/)
- [Verification record](docs/verification.md)
- [Phase 1 implementation review](docs/phase1-review.md)
- [Phase 1B completion and file inventory](docs/phase1b-completion.md)
- [Incident API contracts](docs/api.md)

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
    src/incidentiq/infrastructure/{__init__,memory}.py
    src/incidentiq/api/{__init__,incidents}.py
    tests/test_health.py
    tests/test_incidents.py
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
docs/
  architecture.md
  development.md
  roadmap.md
  verification.md
  phase1-review.md
  phase1b-completion.md
  api.md
  adr/0001-modular-monolith.md
  adr/0002-runtime-and-dependencies.md
  adr/0003-health-and-server-connectivity.md
  adr/0004-future-platform-boundaries.md
  adr/0005-incident-domain-and-ephemeral-storage.md
scripts/smoke.py
.gitignore
README.md
```

Use Python 3.15, Node 24 and npm 11. Run one backend worker and one frontend process.
Never commit `.env`, `.env.local`, API keys or database credentials. `.env.example`
contains only non-secret defaults. CI requires no cloud credentials. This is a foundation,
not a production-ready enterprise application.
