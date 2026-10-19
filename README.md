# IncidentIQ

AI-powered incident investigation platform for learning and portfolio development.
This milestone implements only a FastAPI health API and a Next.js connectivity page.
No database, LLM, MCP, RAG, or LangGraph integration is installed or implemented.

- [Windows setup and commands](docs/development.md)
- [Architecture diagrams](docs/architecture.md)
- [Roadmap and acceptance criteria](docs/roadmap.md)
- [Architecture decisions](docs/adr/)
- [Verification record](docs/verification.md)
- [Phase 1 implementation review](docs/phase1-review.md)

## Repository

```text
.github/workflows/ci.yml
apps/
  api/
    .env.example
    pyproject.toml
    requirements-dev.lock.txt
    src/incidentiq/{__init__,config,main}.py
    tests/test_health.py
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
docs/
  architecture.md
  development.md
  roadmap.md
  verification.md
  phase1-review.md
  adr/0001-modular-monolith.md
  adr/0002-runtime-and-dependencies.md
  adr/0003-health-and-server-connectivity.md
  adr/0004-future-platform-boundaries.md
scripts/smoke.py
.gitignore
README.md
```

Use Python 3.15, Node 24 and npm 11. Run one backend worker and one frontend process.
Never commit `.env`, `.env.local`, API keys or database credentials. `.env.example`
contains only non-secret defaults. CI requires no cloud credentials. This is a foundation,
not a production-ready enterprise application.
