"""HTTP composition root. Future domain modules must remain independent of HTTP."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from incidentiq.api.incidents import incident_router
from incidentiq.application.incidents import (
    IncidentConflict,
    IncidentRepository,
    IncidentService,
    IncidentStorageUnavailable,
)
from incidentiq.config import Settings, load_settings
from incidentiq.infrastructure.database import Database
from incidentiq.infrastructure.memory import InMemoryIncidentRepository
from incidentiq.infrastructure.postgres import PostgresIncidentRepository

logger = logging.getLogger("incidentiq")
logger.setLevel(logging.INFO)


class HealthResponse(BaseModel):
    status: str
    service: str = "incidentiq-api"


class ReadinessResponse(HealthResponse):
    storage: Literal["memory", "postgres"]


def create_app(
    settings: Settings | None = None,
    repository: IncidentRepository | None = None,
) -> FastAPI:
    config = settings if settings is not None else load_settings()
    database = None
    if repository is None and config.persistent:
        assert config.database_url is not None
        database = Database(config.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        app.state.started = True
        try:
            yield
        finally:
            app.state.started = False
            if database is not None:
                database.close()

    app = FastAPI(title="IncidentIQ API", version="0.1.0", lifespan=lifespan)
    app.state.started = False
    incident_repository = (
        repository
        if repository is not None
        else (
            PostgresIncidentRepository(database.sessions)
            if database
            else InMemoryIncidentRepository()
        )
    )
    app.include_router(incident_router(IncidentService(incident_repository)))

    @app.exception_handler(IncidentStorageUnavailable)
    async def storage_failure(
        _request: Request, _error: IncidentStorageUnavailable
    ) -> JSONResponse:
        logger.warning(json.dumps({"event": "incident_storage_unavailable"}))
        return JSONResponse({"detail": "Incident storage unavailable"}, status_code=503)

    @app.exception_handler(IncidentConflict)
    async def storage_conflict(_request: Request, _error: IncidentConflict) -> JSONResponse:
        return JSONResponse({"detail": "Incident could not be stored"}, status_code=409)

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
        response_model=ReadinessResponse,
        responses={503: {"model": ReadinessResponse, "description": "Application is not ready"}},
    )
    def ready(response: Response) -> ReadinessResponse:
        response.headers["Cache-Control"] = "no-store"
        available = app.state.started and config.ready
        if available and database is not None:
            available = database.ready()
        response.status_code = 200 if available else 503
        return ReadinessResponse(
            status="ready" if available else "not_ready",
            storage="postgres" if database is not None else "memory",
        )

    return app


app = create_app()
