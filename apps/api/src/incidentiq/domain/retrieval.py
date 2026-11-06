"""Bounded evidence retrieval contracts and deterministic rank fusion."""

import math
import re
from dataclasses import dataclass, field
from uuid import UUID


class RetrievalFailure(Exception):
    """Only fixed non-sensitive codes cross retrieval boundaries."""


def normalized(vector: tuple[float, ...], dimensions: int) -> tuple[float, ...]:
    if len(vector) != dimensions or any(
        isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
        for v in vector
    ):
        raise RetrievalFailure("embedding_invalid")
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise RetrievalFailure("embedding_invalid")
    return tuple(v / norm for v in vector)


def terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


@dataclass(frozen=True)
class Evidence:
    event_id: UUID
    file_id: UUID
    source_line: int
    source_path: str
    source_commit: str
    file_sha256: str
    text: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not 1 <= self.source_line <= 2000
            or not self.text.strip()
            or len(self.text.encode()) > 8000
            or not re.fullmatch(r"[a-f0-9]{40}", self.source_commit)
            or not re.fullmatch(r"[a-f0-9]{64}", self.file_sha256)
            or not self.source_path
            or len(self.source_path) > 200
        ):
            raise ValueError("evidence_invalid")


@dataclass(frozen=True)
class SearchHit:
    evidence: Evidence
    score: float
    keyword_rank: int | None
    vector_rank: int | None


def fuse(keyword: list[UUID], vector: list[UUID]) -> list[tuple[UUID, float]]:
    """Reciprocal rank fusion (k=60); candidate IDs must be unique per ranking."""
    scores: dict[UUID, float] = {}
    for ranking in (keyword, vector):
        if len(ranking) != len(set(ranking)):
            raise RetrievalFailure("ranking_invalid")
        for rank, identity in enumerate(ranking, 1):
            scores[identity] = scores.get(identity, 0) + 1 / (60 + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
