"""Transactional file snapshots and bounded PostgreSQL FTS/pgvector retrieval."""

import hashlib
import json
from collections.abc import Callable
from functools import wraps
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from incidentiq.domain.retrieval import Evidence, RetrievalFailure, SearchHit, fuse, normalized
from incidentiq.infrastructure.database import Database

TABLE = "incidentiq.retrieval_documents"
SOURCE = """SELECT e.id AS event_id, e.file_id, e.source_line, e.message AS content,
    f.source_path, f.source_commit, f.sha256 AS file_sha256, f.line_count AS expected_line_count
    FROM incidentiq.log_events e JOIN incidentiq.log_files f ON f.id=e.file_id
    WHERE e.file_id=:file_id ORDER BY e.source_line LIMIT 2001"""

# One statement keeps both candidate branches and citations on one MVCC snapshot.
SEARCH = """WITH scoped AS MATERIALIZED (
    SELECT d.*, e.source_line, e.message AS source_content,
        f.source_path, f.source_commit, f.sha256 AS file_sha256
    FROM incidentiq.retrieval_documents d
    JOIN incidentiq.log_events e ON e.id=d.event_id AND e.file_id=d.file_id
    JOIN incidentiq.log_files f ON f.id=d.file_id WHERE d.file_id=:file_id
), keyword AS (
    SELECT event_id, row_number() OVER (ORDER BY
        ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query)) DESC,
        event_id) AS rank
    FROM scoped WHERE model=:model AND dimensions=512
        AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
    ORDER BY rank LIMIT 50
), semantic AS (
    SELECT event_id, row_number() OVER (ORDER BY
        embedding OPERATOR(extensions.<=>) CAST(:vector AS extensions.vector(512)),
        event_id) AS rank
    FROM scoped WHERE model=:model AND dimensions=512
        AND (embedding OPERATOR(extensions.<=>) CAST(:vector AS extensions.vector(512))) < 1
    ORDER BY rank LIMIT 50
)
SELECT s.event_id, s.file_id, s.source_line, s.source_path, s.source_commit,
    s.file_sha256, s.content, s.source_content, s.content_sha256, s.model, s.dimensions,
    k.rank AS keyword_rank, v.rank AS vector_rank
FROM scoped s LEFT JOIN keyword k ON k.event_id=s.event_id
LEFT JOIN semantic v ON v.event_id=s.event_id
WHERE k.event_id IS NOT NULL OR v.event_id IS NOT NULL
    OR s.model<>:model OR s.dimensions<>512
ORDER BY s.event_id LIMIT 2001"""


def safe_retrieval(function: Callable) -> Callable:
    @wraps(function)
    def protected(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SQLAlchemyError:
            raise RetrievalFailure("retrieval_storage_unavailable") from None

    return protected


def source_evidence(row) -> Evidence:
    return Evidence(
        row["event_id"],
        row["file_id"],
        row["source_line"],
        row["source_path"],
        row["source_commit"],
        row["file_sha256"],
        row["content"],
    )


def validate_model(model: str, dimensions: int) -> None:
    if not model.strip() or len(model) > 80 or dimensions != 512:
        raise ValueError("retrieval_model_invalid")


class PostgresRetrievalIndex:
    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions

    @staticmethod
    def _lock(session, file_id):
        # Shared key for replace/delete, transaction scoped for pooler compatibility.
        session.execute(text("SET LOCAL lock_timeout='2000ms'"))
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 1938463))"),
            {"scope": f"retrieval:{file_id}"},
        )

    @safe_retrieval
    def load_file(self, file_id: UUID) -> list[Evidence]:
        with self.sessions() as session:
            Database.bound_statement(session)
            rows = session.execute(text(SOURCE), {"file_id": file_id}).mappings().all()
            if not 1 <= len(rows) <= 2000:
                raise RetrievalFailure("retrieval_source_unavailable")
            if len(rows) != rows[0]["expected_line_count"]:
                raise RetrievalFailure("retrieval_source_incomplete")
            return [source_evidence(row) for row in rows]

    @safe_retrieval
    def matches_file(self, file_id, evidence, model, dimensions) -> bool:
        validate_model(model, dimensions)
        with self.sessions() as session:
            Database.bound_statement(session)
            rows = (
                session.execute(
                    text(f"""SELECT event_id, model, dimensions,
                content_sha256, content FROM {TABLE} WHERE file_id=:file_id LIMIT 2001"""),
                    {"file_id": file_id},
                )
                .mappings()
                .all()
            )
        expected = {item.event_id: item for item in evidence}
        return len(rows) == len(expected) and all(
            row["event_id"] in expected
            and row["model"] == model
            and row["dimensions"] == dimensions
            and row["content"] == expected[row["event_id"]].text
            and row["content_sha256"] == hashlib.sha256(row["content"].encode()).hexdigest()
            for row in rows
        )

    @safe_retrieval
    def replace_file(
        self,
        file_id: UUID,
        evidence: list[Evidence],
        vectors: list[tuple[float, ...]],
        model: str,
        dimensions: int,
    ) -> None:
        validate_model(model, dimensions)
        if not 1 <= len(evidence) <= 2000 or len(evidence) != len(vectors):
            raise ValueError("index_evidence_invalid")
        if any(e.file_id != file_id for e in evidence) or len(
            {e.event_id for e in evidence}
        ) != len(evidence):
            raise ValueError("index_evidence_invalid")
        values = [
            {
                "event_id": e.event_id,
                "file_id": file_id,
                "model": model,
                "digest": hashlib.sha256(e.text.encode()).hexdigest(),
                "content": e.text,
                "vector": json.dumps(normalized(v, 512), allow_nan=False),
            }
            for e, v in zip(evidence, vectors, strict=True)
        ]
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            self._lock(session, file_id)
            if session.scalar(text("SELECT pg_database_size(current_database())")) > 400 * 1024**2:
                raise RetrievalFailure("retrieval_storage_budget_exceeded")
            # Protect provenance and source content while validating/publishing the snapshot.
            session.execute(
                text("SELECT id FROM incidentiq.log_files WHERE id=:file_id FOR UPDATE"),
                {"file_id": file_id},
            )
            session.execute(
                text("SELECT id FROM incidentiq.log_events WHERE file_id=:file_id FOR SHARE"),
                {"file_id": file_id},
            )
            rows = session.execute(text(SOURCE), {"file_id": file_id}).mappings().all()
            if rows and len(rows) != rows[0]["expected_line_count"]:
                raise RetrievalFailure("retrieval_source_incomplete")
            actual = [source_evidence(row) for row in rows]
            if sorted(actual, key=lambda e: e.source_line) != sorted(
                evidence, key=lambda e: e.source_line
            ):
                raise RetrievalFailure("retrieval_source_changed")
            session.execute(
                text(f"DELETE FROM {TABLE} WHERE file_id=:file_id"), {"file_id": file_id}
            )
            statement = text(f"""INSERT INTO {TABLE}
                (event_id, file_id, model, dimensions,
                 content_sha256, content, embedding, indexed_at)
                VALUES (:event_id, :file_id, :model, 512, :digest, :content,
                        CAST(:vector AS extensions.vector(512)), CURRENT_TIMESTAMP)""")
            for offset in range(0, len(values), 16):
                session.execute(statement, values[offset : offset + 16])

    @safe_retrieval
    def delete_file(self, file_id: UUID) -> int:
        with self.sessions.begin() as session:
            Database.bound_statement(session)
            self._lock(session, file_id)
            result = session.execute(
                text(f"DELETE FROM {TABLE} WHERE file_id=:file_id"), {"file_id": file_id}
            )
            return result.rowcount

    @safe_retrieval
    def search(
        self,
        file_id: UUID,
        query: str,
        vector: tuple[float, ...],
        model: str,
        dimensions: int,
        limit: int,
        mode: str = "hybrid",
    ) -> list[SearchHit]:
        validate_model(model, dimensions)
        if mode not in {"keyword", "vector", "hybrid"}:
            raise ValueError("search_mode_invalid")
        if (
            not query.strip()
            or len(query.encode()) > 800
            or type(limit) is not int
            or not 1 <= limit <= 20
        ):
            raise ValueError("search_bounds_invalid")
        vector_text = json.dumps(normalized(vector, 512), allow_nan=False)
        with self.sessions() as session:
            Database.bound_statement(session)
            rows = (
                session.execute(
                    text(SEARCH),
                    {"file_id": file_id, "query": query, "model": model, "vector": vector_text},
                )
                .mappings()
                .all()
            )
        if any(row["model"] != model or row["dimensions"] != dimensions for row in rows):
            raise RetrievalFailure("embedding_model_mismatch")
        if any(
            row["source_content"] != row["content"]
            or row["content_sha256"] != hashlib.sha256(row["content"].encode()).hexdigest()
            for row in rows
        ):
            raise RetrievalFailure("retrieval_source_changed")
        keyword = [
            row["event_id"]
            for row in sorted(
                (r for r in rows if r["keyword_rank"] is not None), key=lambda r: r["keyword_rank"]
            )
        ]
        semantic = [
            row["event_id"]
            for row in sorted(
                (r for r in rows if r["vector_rank"] is not None), key=lambda r: r["vector_rank"]
            )
        ]
        by_id = {row["event_id"]: row for row in rows}
        ranked = fuse(keyword, semantic)
        if mode != "hybrid":
            ranking = keyword if mode == "keyword" else semantic
            ranked = [(identity, 1 / (60 + rank)) for rank, identity in enumerate(ranking, 1)]
        return [
            SearchHit(
                source_evidence(by_id[identity]),
                score,
                by_id[identity]["keyword_rank"],
                by_id[identity]["vector_rank"],
            )
            for identity, score in ranked[:limit]
        ]
