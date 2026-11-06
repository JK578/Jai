"""Offline/reference index: BM25 keyword ranks, exact cosine ranks and RRF."""

import math
from collections import Counter
from threading import Lock
from uuid import UUID

from incidentiq.domain.retrieval import (
    Evidence,
    RetrievalFailure,
    SearchHit,
    fuse,
    normalized,
    terms,
)


class InMemoryRetrievalIndex:
    def __init__(self):
        self._files: dict[UUID, tuple] = {}
        self._lock = Lock()

    def replace_file(
        self,
        file_id: UUID,
        evidence: list[Evidence],
        vectors: list[tuple[float, ...]],
        model: str,
        dimensions: int,
    ) -> None:
        if len(evidence) != len(vectors):
            raise RetrievalFailure("embedding_invalid")
        staged = tuple(zip(evidence, (normalized(v, dimensions) for v in vectors), strict=True))
        with self._lock:
            if file_id not in self._files and len(self._files) >= 4:
                raise RetrievalFailure("index_capacity_exceeded")
            self._files[file_id] = (model, dimensions, staged)

    def delete_file(self, file_id: UUID) -> int:
        with self._lock:
            existing = self._files.pop(file_id, None)
            return len(existing[2]) if existing else 0

    def search(
        self,
        file_id: UUID,
        query: str,
        vector: tuple[float, ...],
        model: str,
        dimensions: int,
        limit: int,
    ) -> list[SearchHit]:
        with self._lock:
            snapshot = self._files.get(file_id)
        if snapshot is None:
            return []
        if snapshot[:2] != (model, dimensions):
            raise RetrievalFailure("embedding_model_mismatch")
        rows = snapshot[2]
        query_vector = normalized(vector, dimensions)
        documents = [Counter(terms(item.text)) for item, _ in rows]
        average = sum(sum(doc.values()) for doc in documents) / max(1, len(documents))
        keyword_scores = []
        query_terms = set(terms(query))
        frequencies = {term: sum(term in doc for doc in documents) for term in query_terms}
        for (item, _), doc in zip(rows, documents, strict=True):
            score = 0.0
            for term in query_terms:
                count = doc[term]
                if count:
                    idf = math.log(
                        1 + (len(rows) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                    )
                    score += (
                        idf
                        * count
                        * 2.2
                        / (count + 1.2 * (0.25 + 0.75 * sum(doc.values()) / max(1, average)))
                    )
            if score > 0:
                keyword_scores.append((item.event_id, score))
        vector_scores = [
            (item.event_id, sum(a * b for a, b in zip(query_vector, v, strict=True)))
            for item, v in rows
        ]
        # No forced semantic match for orthogonal/negative candidates.
        keyword = [
            identity
            for identity, _ in sorted(keyword_scores, key=lambda x: (-x[1], str(x[0])))[:50]
        ]
        vector_ids = [
            identity
            for identity, score in sorted(vector_scores, key=lambda x: (-x[1], str(x[0])))[:50]
            if score > 0
        ]
        evidence = {item.event_id: item for item, _ in rows}
        kr = {identity: i for i, identity in enumerate(keyword, 1)}
        vr = {identity: i for i, identity in enumerate(vector_ids, 1)}
        return [
            SearchHit(evidence[identity], score, kr.get(identity), vr.get(identity))
            for identity, score in fuse(keyword, vector_ids)[:limit]
        ]
