# ADR 0002: Preserve Python 3.15 and verify native dependencies

Status: Accepted

Decision: Require Python 3.15 and Node 24; keep the existing virtual environment.
FastAPI 0.149.0 and Pydantic 2.14.1 are explicit choices. Install binary wheels to detect
unsupported native extensions instead of unexpectedly compiling Rust/C++ locally.
Capture the validated Python environment in requirements-dev.lock.txt and npm resolution
in package-lock.json. CI uses these resolutions. Change them deliberately together with
the manifests. Do not downgrade or substitute libraries silently.

Risk: pydantic-core requires a compatible Windows CPython wheel. Future SQLAlchemy drivers,
LangGraph dependencies, tokenizers and vector tooling must be checked separately on 3.15.
Successful installation today cannot establish compatibility of uninstalled future packages.
Use plain uvicorn rather than its optional native performance extras.

Observed compatibility tradeoffs: ESLint 9.39.5 is unsupported upstream, but the current
React and accessibility lint plugins exclude ESLint 10 from their peer ranges. Retain 9
without forcing incompatible peers. Starlette's HTTPX TestClient path emits a deprecation
warning; retain the tested transport for now and track migration separately. Neither warning
was hidden, and neither implies Python 3.15 installation failed.

References: https://pypi.org/project/pydantic/ and
https://nextjs.org/docs/app/getting-started/installation
