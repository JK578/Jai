"""HTTP composition root. Future domain modules must remain independent of HTTP."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from incidentiq.api.incidents import incident_router
from incidentiq.application.incidents import IncidentRepository, IncidentService
from incidentiq.config import Settings, load_settings
from incidentiq.infrastructure.memory import InMemoryIncidentRepository

logger = logging.getLogger("incidentiq")
logger.setLevel(logging.INFO)


class HealthResponse(BaseModel):
    status: str
    service: str = "incidentiq-api"


def create_app(
    settings: Settings | None = None,
    repository: IncidentRepository | None = None,
) -> FastAPI:
    config = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        app.state.started = True
        try:
            yield
        finally:
            app.state.started = False

    app = FastAPI(title="IncidentIQ API", version="0.1.0", lifespan=lifespan)
    app.state.started = False
    incident_repository = repository if repository is not None else InMemoryIncidentRepository()
    app.include_router(incident_router(IncidentService(incident_repository)))

    @app.middleware("http")
    async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        response = await call_next(request)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.get("/health/live", response_model=HealthResponse)
    async def live(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status="alive")

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse, "description": "Application is not ready"}},
    )
    async def ready(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        available = app.state.started and config.ready
        response.status_code = 200 if available else 503
        return HealthResponse(status="ready" if available else "not_ready")

    return app


app = create_app()
