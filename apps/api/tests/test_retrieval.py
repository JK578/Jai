import json
from dataclasses import replace
from uuid import UUID

import httpx
import pytest
from incidentiq.application.retrieval import RetrievalService
from incidentiq.domain.retrieval import Evidence, RetrievalFailure, fuse, normalized
from incidentiq.infrastructure.embedding_provider import OpenAIEmbeddingProvider
from incidentiq.infrastructure.retrieval_memory import InMemoryRetrievalIndex
from pydantic import SecretStr

from scripts.evaluate_retrieval import evaluate

FILE = UUID(int=100)


def test_evaluation_reproducible_and_explicitly_synthetic():
    first = evaluate()
    assert evaluate() == first
    assert first["deletion_verified"]
    assert first["embedding_model"] == "curated-fixture-v1"
    assert first["metrics"]["hybrid"] == {"recall_at_1": 1.0, "mrr": 1.0}
    assert first["metrics"]["keyword"]["recall_at_1"] == 0.333333


def test_index_batches_and_late_failure_is_atomic():
    engine = service()
    original = evidence(1, "restart")
    engine.index_file(FILE, [original])
    calls = []

    def embed(texts):
        calls.append(len(texts))
        if len(calls) == 2:
            raise RetrievalFailure("embedding_timeout")
        return [(1, 0, 0)] * len(texts)

    engine.provider.embed = embed
    with pytest.raises(RetrievalFailure, match="embedding_timeout"):
        engine.index_file(FILE, [evidence(n, "restart") for n in range(1, 18)])
    assert calls == [16, 1]
    engine.provider = FixtureEmbeddings()
    assert engine.search(FILE, "restart")[0].evidence == original


def evidence(number, text, file_id=FILE):
    return Evidence(UUID(int=number), file_id, number, "synthetic.log", "a" * 40, "b" * 64, text)


class FixtureEmbeddings:
    # Controlled semantic labels test retrieval mechanics, not real embedding quality.
    model = "fixture-v1"
    dimensions = 3

    def embed(self, texts):
        groups = {
            "restart": 0,
            "terminated": 0,
            "shutdown": 0,
            "permissions": 1,
            "forbidden": 1,
            "denied": 1,
            "healthy": 2,
            "started": 2,
        }
        result = []
        for text in texts:
            vector = [0.0, 0.0, 0.0]
            for word, index in groups.items():
                if word in text.lower():
                    vector[index] = 1.0
            result.append(tuple(vector) if any(vector) else (0.0, 0.0, 1.0))
        return result


def service():
    return RetrievalService(FixtureEmbeddings(), InMemoryRetrievalIndex())


def test_hybrid_retrieval_reproducible_citations_and_deletion():
    engine = service()
    corpus = [
        evidence(1, "Server terminated unexpectedly"),
        evidence(2, "Request forbidden: access denied"),
        evidence(3, "Server started healthy"),
    ]
    assert engine.index_file(FILE, corpus) == 3
    first = engine.search(FILE, "restart")
    assert first[0].evidence == corpus[0]
    assert first[0].keyword_rank is None and first[0].vector_rank == 1
    assert engine.search(FILE, "permissions")[0].evidence == corpus[1]
    assert engine.search(FILE, "healthy")[0].evidence == corpus[2]
    assert engine.index_file(FILE, corpus) == 3
    assert engine.search(FILE, "restart") == first
    assert first[0].evidence.source_line == 1
    assert first[0].evidence.file_sha256 == "b" * 64
    assert engine.delete_file(FILE) == 3
    assert engine.search(FILE, "restart") == []
    assert engine.delete_file(FILE) == 0


def test_file_scope_and_model_mismatch():
    engine = service()
    engine.index_file(FILE, [evidence(1, "restart")])
    other = UUID(int=101)
    engine.index_file(other, [evidence(2, "restart", other)])
    assert engine.search(FILE, "restart")[0].evidence.file_id == FILE
    assert engine.delete_file(FILE) == 1
    assert len(engine.search(other, "restart")) == 1
    engine.provider.model = "different"
    with pytest.raises(RetrievalFailure, match="embedding_model_mismatch"):
        engine.search(other, "restart")


def test_failed_rebuild_preserves_previous_snapshot():
    engine = service()
    original = evidence(1, "restart")
    engine.index_file(FILE, [original])
    engine.provider.embed = lambda texts: [(float("nan"), 0, 1)]
    with pytest.raises(RetrievalFailure, match="embedding_invalid"):
        engine.index_file(FILE, [evidence(2, "healthy")])
    engine.provider = FixtureEmbeddings()
    assert engine.search(FILE, "restart")[0].evidence == original


def test_invalid_source_and_duplicate_identity_before_embedding():
    engine = service()
    item = evidence(1, "restart")
    for corpus in (
        [],
        [item, item],
        [replace(item, file_id=UUID(int=999))],
        [item, replace(evidence(2, "healthy"), file_sha256="c" * 64)],
    ):
        with pytest.raises(ValueError, match="index_evidence_invalid"):
            engine.index_file(FILE, corpus)


@pytest.mark.parametrize(
    "query,limit", [("", 5), ("x" * 801, 5), ("restart", 0), ("restart", 21), ("restart", True)]
)
def test_search_bounds(query, limit):
    with pytest.raises(ValueError, match="search_bounds_invalid"):
        service().search(FILE, query, limit)


@pytest.mark.parametrize(
    "vector", [(0, 0), (float("inf"), 1), (float("nan"), 1), (True, 1), (1,), (1, "x")]
)
def test_invalid_vectors(vector):
    with pytest.raises(RetrievalFailure, match="embedding_invalid"):
        normalized(vector, 2)


def test_rank_fusion_agreement_and_tie_break():
    a, b, c = (UUID(int=n) for n in (1, 2, 3))
    result = fuse([a, b], [c, b])
    assert result[0][0] == b
    assert result[1][0] == a
    with pytest.raises(RetrievalFailure, match="ranking_invalid"):
        fuse([a, a], [])


def provider(handler, budget=20000):
    return OpenAIEmbeddingProvider(
        SecretStr("private-key"), budget, transport=httpx.MockTransport(handler)
    )


def embedding_payload():
    return {
        "model": "text-embedding-3-small",
        "data": [
            {"index": 1, "embedding": [0, 1] + [0] * 510},
            {"index": 0, "embedding": [1, 0] + [0] * 510},
        ],
        "usage": {"total_tokens": 2},
    }


def test_openai_embedding_wire_order_and_budget():
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/embeddings"
        assert json.loads(request.content) == {
            "model": "text-embedding-3-small",
            "dimensions": 512,
            "encoding_format": "float",
            "input": ["restart", "healthy"],
        }
        return httpx.Response(200, json=embedding_payload())

    embedder = provider(handler)
    result = embedder.embed(["restart", "healthy"])
    assert result[0][0] == 1 and result[1][1] == 1
    assert embedder.remaining_microusd == 19998


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "embedding_authentication_failed"),
        (429, "embedding_rate_limited"),
        (500, "embedding_unavailable"),
        (302, "embedding_unavailable"),
    ],
)
def test_embedding_safe_failure_no_retry(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-key")

    embedder = provider(handler)
    with pytest.raises(RetrievalFailure, match=f"^{code}$"):
        embedder.embed(["restart"])
    assert len(calls) == 1
    assert embedder.remaining_microusd == 19993


def test_embedding_timeout_and_budget_rejection():
    def handler(request):
        raise httpx.ReadTimeout("private-key")

    embedder = provider(handler, budget=7)
    with pytest.raises(RetrievalFailure, match="embedding_budget_exceeded"):
        embedder.embed(["restart healthy"])
    assert embedder.remaining_microusd == 7
    with pytest.raises(RetrievalFailure, match="^embedding_timeout$"):
        embedder.embed(["restart"])
    assert embedder.remaining_microusd == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(model="different"),
        lambda p: p["data"][0].update(index=0),
        lambda p: p["data"][0].update(embedding=[1, 0]),
        lambda p: p["usage"].update(total_tokens=True),
        lambda p: p["usage"].update(total_tokens=99999),
    ],
)
def test_embedding_response_validation(mutate):
    body = embedding_payload()
    mutate(body)
    with pytest.raises(RetrievalFailure, match="embedding_invalid"):
        provider(lambda r: httpx.Response(200, json=body)).embed(["restart", "healthy"])
