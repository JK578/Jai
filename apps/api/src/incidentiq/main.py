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
from starlette.middleware.trustedhost import TrustedHostMiddleware

from incidentiq.api.hardening import BodyLimit, RequestRate
from incidentiq.api.incidents import incident_router
from incidentiq.api.logs import LogReader, log_router
from incidentiq.api.workspace import workspace_router
from incidentiq.application.access import current_principal, required_scope
from incidentiq.application.incidents import (
    IncidentConflict,
    IncidentRepository,
    IncidentService,
    IncidentStorageUnavailable,
)
from incidentiq.config import Settings, load_settings
from incidentiq.domain.access import AccessDenied
from incidentiq.domain.logs import LogUnavailable
from incidentiq.infrastructure.access import TokenRegistry
from incidentiq.infrastructure.database import Database
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.memory import InMemoryIncidentRepository
from incidentiq.infrastructure.postgres import PostgresIncidentRepository
from incidentiq.infrastructure.scoped_services import ScopedIncidentService, ScopedLogReader

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
    log_repository: LogReader | None = None,
) -> FastAPI:
    config = settings if settings is not None else load_settings()
    database = None
    if repository is None and config.persistent:
        assert config.database_url is not None
        database = Database(
            config.runtime_database_url if config.auth_enabled else config.database_url
        )

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
    rate = RequestRate()
    app.add_middleware(BodyLimit)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost"]
        + (["testserver"] if config.environment != "production" else []),
    )
    incident_repository = (
        repository
        if repository is not None
        else (
            PostgresIncidentRepository(database.sessions)
            if database
            else InMemoryIncidentRepository()
        )
    )
    app.include_router(
        incident_router(
            ScopedIncidentService(database)
            if config.auth_enabled
            else IncidentService(incident_repository)
        )
    )
    app.include_router(workspace_router(database, config.data_dir))
    app.include_router(
        log_router(
            log_repository
            or (
                (
                    ScopedLogReader(database)
                    if config.auth_enabled
                    else PostgresLogRepository(database.sessions)
                )
                if database
                else None
            )
        )
    )

    @app.exception_handler(LogUnavailable)
    async def log_storage_failure(_request: Request, _error: LogUnavailable) -> JSONResponse:
        return JSONResponse({"detail": "Log storage unavailable"}, status_code=503)

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
        context_token = None
        try:
            if config.auth_enabled and request.url.path.startswith("/api/"):
                header = request.headers.get("Authorization", "")
                if not header.startswith("Bearer "):
                    raise AccessDenied("authentication_required")
                actor = TokenRegistry(config.token_registry).authenticate(header[7:])
                if not rate.allowed(actor.user_id):
                    raise AccessDenied("rate_limited")
                scope = required_scope(request.method, request.url.path)
                if scope and not actor.permits(scope):
                    raise AccessDenied("permission_denied")
                context_token = current_principal.set(actor)
            response = await call_next(request)
        except AccessDenied as error:
            if str(error) == "rate_limited":
                return JSONResponse(
                    {"detail": "Request limit reached"},
                    status_code=429,
                    headers={"Retry-After": "60", "Cache-Control": "no-store"},
                )
            denied = str(error) == "permission_denied"
            response = JSONResponse(
                {"detail": "Permission denied" if denied else "Authentication required"},
                status_code=403 if denied else 401,
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
            )
        finally:
            if context_token is not None:
                current_principal.reset(context_token)
        if config.auth_enabled and request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization"
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "path": getattr(request.scope.get("route"), "path", "/unmatched"),
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.get("/api/v1/auth/session")
    def session_identity():
        actor = current_principal.get()
        if actor is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return {
            "user_id": str(actor.user_id),
            "tenant_id": str(actor.tenant_id),
            "scopes": sorted(actor.scopes),
        }

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
            if available and config.auth_enabled:
                available = database.restricted()
        response.status_code = 200 if available else 503
        return ReadinessResponse(
            status="ready" if available else "not_ready",
            storage="postgres" if database is not None else "memory",
        )

    return app


app = create_app()
