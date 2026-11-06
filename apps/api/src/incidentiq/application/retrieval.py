"""Explicit indexing and file-scoped hybrid search; never starts work on API startup."""

from typing import Protocol
from uuid import UUID

from incidentiq.domain.retrieval import Evidence, RetrievalFailure, SearchHit, normalized


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class RetrievalIndex(Protocol):
    def replace_file(
        self,
        file_id: UUID,
        evidence: list[Evidence],
        vectors: list[tuple[float, ...]],
        model: str,
        dimensions: int,
    ) -> None: ...

    def search(
        self,
        file_id: UUID,
        query: str,
        vector: tuple[float, ...],
        model: str,
        dimensions: int,
        limit: int,
    ) -> list[SearchHit]: ...

    def delete_file(self, file_id: UUID) -> int: ...


class RetrievalService:
    def __init__(self, provider: EmbeddingProvider, index: RetrievalIndex):
        self.provider, self.index = provider, index

    def index_file(self, file_id: UUID, evidence: list[Evidence]) -> int:
        if (
            not 1 <= len(evidence) <= 2000
            or any(item.file_id != file_id for item in evidence)
            or len({item.event_id for item in evidence}) != len(evidence)
            or len({item.source_line for item in evidence}) != len(evidence)
            or len({(item.file_sha256, item.source_commit, item.source_path) for item in evidence})
            != 1
        ):
            raise ValueError("index_evidence_invalid")
        # Stage the full bounded corpus; publish only after all batches succeed.
        vectors = []
        for offset in range(0, len(evidence), 16):
            batch = evidence[offset : offset + 16]
            result = self.provider.embed([item.text for item in batch])
            if len(result) != len(batch):
                raise RetrievalFailure("embedding_invalid")
            vectors.extend(normalized(v, self.provider.dimensions) for v in result)
        self.index.replace_file(
            file_id, evidence, vectors, self.provider.model, self.provider.dimensions
        )
        return len(evidence)

    def search(self, file_id: UUID, query: str, limit: int = 5) -> list[SearchHit]:
        if (
            not query.strip()
            or len(query.encode()) > 800
            or type(limit) is not int
            or not 1 <= limit <= 20
        ):
            raise ValueError("search_bounds_invalid")
        result = self.provider.embed([query])
        if len(result) != 1:
            raise RetrievalFailure("embedding_invalid")
        vector = normalized(result[0], self.provider.dimensions)
        return self.index.search(
            file_id, query, vector, self.provider.model, self.provider.dimensions, limit
        )

    def delete_file(self, file_id: UUID) -> int:
        return self.index.delete_file(file_id)
