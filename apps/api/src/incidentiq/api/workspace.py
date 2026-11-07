"""Authenticated, budgeted retrieval and user-owned investigation workflow routes."""

import json
from dataclasses import asdict
from pathlib import Path
from threading import BoundedSemaphore
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from incidentiq.application.access import principal
from incidentiq.application.retrieval import RetrievalService
from incidentiq.domain.access import AccessDenied
from incidentiq.domain.investigations import InvestigationFailure
from incidentiq.infrastructure.access import ScopedSessions
from incidentiq.infrastructure.embedding_provider import OpenAIEmbeddingProvider
from incidentiq.infrastructure.log_source import manifest
from incidentiq.infrastructure.retrieval_postgres import PostgresRetrievalIndex
from incidentiq.infrastructure.usage_budget import UsageBudget

MODEL_SLOT = BoundedSemaphore(1)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=800)
    provider: Literal["mock", "openai"] = "mock"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    report_sha256: str = Field(pattern="^[a-f0-9]{64}$")


class SearchQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=800)


def workspace_router(database, private: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["workspace"])
    budget = UsageBudget(private / "access/usage.sqlite")

    def scoped():
        actor = principal()
        if database is None:
            raise HTTPException(503, "Persistent workspace unavailable")
        sessions = ScopedSessions(database.sessions, actor)
        with sessions() as session:
            visible = session.scalar(
                text("SELECT id FROM incidentiq.log_files WHERE id=:id"), {"id": manifest().file_id}
            )
        if visible is None:
            raise HTTPException(404, "Log file not found")
        return actor, PostgresRetrievalIndex(sessions)

    def embedder(amount):
        import os

        from pydantic import SecretStr

        return OpenAIEmbeddingProvider(SecretStr(os.getenv("OPENAI_API_KEY", "")), amount)

    def operation(action, identity=None, request=None, decision=None):
        from scripts.investigate import execute

        actor, index = scoped()
        if request and len(request.question.encode()) > 800:
            raise HTTPException(422, "Question is too long")
        root = private / "investigations-web" / str(actor.tenant_id) / str(actor.user_id)
        if identity and not (root / str(identity) / "checkpoints.sqlite").exists():
            raise HTTPException(404, "Investigation not found")
        if not MODEL_SLOT.acquire(blocking=False):
            raise HTTPException(429, "Another model operation is running; retry shortly")
        try:
            if request and request.provider == "openai":
                budget.reserve(actor.user_id, 20000)
            if action == "retry":
                budget.reserve(actor.user_id, 20000)

            def retrieve(question, file_id):
                hits = RetrievalService(embedder(len(question.encode())), index).search(
                    UUID(file_id), question, 5
                )
                return [
                    {
                        **asdict(hit.evidence),
                        "event_id": str(hit.evidence.event_id),
                        "file_id": str(hit.evidence.file_id),
                        "text": hit.evidence.text.encode()[:1200].decode("utf-8", errors="ignore"),
                    }
                    for hit in hits
                ]

            args = SimpleNamespace(
                operation=action,
                run_id=str(identity) if identity else "",
                question=request.question if request else "",
                provider=request.provider if request else "mock",
                report_sha256=decision.report_sha256 if decision else "",
                budget_microusd=20000,
            )
            result = execute(args, run_root=root, retrieve=retrieve)
            from scripts.retrieval_cli import save

            save(
                root / result["run_id"] / "summary.json",
                {key: result[key] for key in ("run_id", "question", "status", "provider")},
            )
            return result
        except InvestigationFailure as error:
            raise HTTPException(409, str(error)) from None
        except AccessDenied:
            raise HTTPException(429, "Daily model budget reached") from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Investigation unavailable") from None
        finally:
            MODEL_SLOT.release()

    @router.post("/search")
    def search(request: SearchQuestion):
        actor, index = scoped()
        if len(request.question.encode()) > 800:
            raise HTTPException(422, "Question is too long")
        if not MODEL_SLOT.acquire(blocking=False):
            raise HTTPException(429, "Another model operation is running")
        try:
            budget.reserve(actor.user_id, len(request.question.encode()))
            hits = RetrievalService(embedder(len(request.question.encode())), index).search(
                manifest().file_id, request.question, 5
            )
            return {"items": [{**asdict(hit.evidence), "score": hit.score} for hit in hits]}
        except AccessDenied:
            raise HTTPException(429, "Daily model budget reached") from None
        except Exception:
            raise HTTPException(503, "Search unavailable") from None
        finally:
            MODEL_SLOT.release()

    @router.post("/investigations")
    def start(request: Question):
        return operation("start", request=request)

    @router.get("/investigations")
    def history():
        actor = principal()
        root = private / "investigations-web" / str(actor.tenant_id) / str(actor.user_id)
        rows = []
        for path in sorted(
            root.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:32]:
            if path.stat().st_size <= 4096:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
        return {"items": rows}

    @router.get("/investigations/{identity}")
    def status(identity: UUID):
        return operation("status", identity)

    @router.post("/investigations/{identity}/retry")
    def retry(identity: UUID):
        return operation("retry", identity)

    @router.post("/investigations/{identity}/resume")
    def resume(identity: UUID):
        return operation("resume", identity)

    @router.post("/investigations/{identity}/{action}")
    def decide(identity: UUID, action: Literal["approve", "reject"], request: Decision):
        return operation(action, identity, decision=request)

    return router
