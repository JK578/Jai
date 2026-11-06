"""Read-only log APIs. Starting ingestion is restricted to an explicit local CLI."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from incidentiq.domain.logs import LogUnavailable
from incidentiq.infrastructure.log_source import manifest


class LogReader(Protocol):
    def read(self, resource: str, **kwargs: Any) -> list[dict[str, Any]]: ...


class Page(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: int | None = None


Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[int, Query(ge=0, le=2000)]
Level = Literal["emergency", "alert", "critical", "error", "warning", "notice", "info", "debug"]
State = Literal["running", "interrupted", "completed", "partial", "failed"]


def log_router(repository: LogReader | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["logs"])

    def read(resource: str, **kwargs: Any) -> list[dict[str, Any]]:
        if repository is None:
            raise LogUnavailable("log_storage_unavailable")
        return repository.read(resource, **kwargs)

    @router.get("/log-datasets", response_model=Page)
    def datasets(response: Response) -> Page:
        response.headers["Cache-Control"] = "no-store"
        source = manifest()
        files = read("files", limit=100)
        return Page(
            items=[
                {
                    **asdict(source),
                    "id": source.dataset_id,
                    "file_id": source.file_id,
                    "files": files,
                }
            ]
        )

    @router.get("/log-ingestions", response_model=Page)
    def runs(
        limit: Limit = 50,
        cursor: Annotated[int, Query(ge=0, le=10000)] = 0,
        file_id: UUID | None = None,
        state: State | None = None,
    ) -> Page:
        # Bounded offset for the small audit history; event pages use stable source-line cursors.
        items = read("runs", limit=limit + 1, offset=cursor, file_id=file_id, state=state)
        return Page(items=items[:limit], next_cursor=cursor + limit if len(items) > limit else None)

    @router.get("/log-ingestions/{run_id}", response_model=dict[str, Any])
    def run(run_id: UUID) -> dict[str, Any]:
        items = read("runs", identity=run_id, limit=1)
        if not items:
            raise HTTPException(404, "Ingestion run not found")
        return items[0]

    @router.get("/log-ingestions/{run_id}/errors", response_model=Page)
    def errors(run_id: UUID, limit: Limit = 50, cursor: Cursor = 0) -> Page:
        run(run_id)
        items = read("errors", identity=run_id, after=cursor, limit=limit + 1)
        return Page(
            items=items[:limit],
            next_cursor=items[limit - 1]["source_line"] if len(items) > limit else None,
        )

    @router.get("/logs", response_model=Page)
    def logs(
        file_id: UUID,
        limit: Limit = 50,
        cursor: Cursor = 0,
        level: Level | None = None,
        q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        from_local: datetime | None = None,
        to_local: datetime | None = None,
    ) -> Page:
        if any(value is not None and value.tzinfo is not None for value in (from_local, to_local)):
            raise HTTPException(422, "Use source-local timestamps without a timezone")
        if from_local and to_local and from_local > to_local:
            raise HTTPException(422, "Invalid source-local time range")
        items = read(
            "events",
            file_id=file_id,
            after=cursor,
            limit=limit + 1,
            level=level,
            q=q,
            from_local=from_local,
            to_local=to_local,
        )
        return Page(
            items=items[:limit],
            next_cursor=items[limit - 1]["source_line"] if len(items) > limit else None,
        )

    @router.get("/logs/{log_id}", response_model=dict[str, Any])
    def log(log_id: UUID) -> dict[str, Any]:
        items = read("events", identity=log_id, limit=1)
        if not items:
            raise HTTPException(404, "Log event not found")
        return items[0]

    return router
