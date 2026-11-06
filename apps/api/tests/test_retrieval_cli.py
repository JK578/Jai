from uuid import UUID

import pytest
from incidentiq.domain.retrieval import Evidence, RetrievalFailure

from scripts import retrieval_cli


class FakeIndex:
    def __init__(self, count=17):
        self.evidence = [
            Evidence(
                UUID(int=n), UUID(int=100), n, "fixture", "a" * 40, "b" * 64, f"unique text {n}"
            )
            for n in range(1, count + 1)
        ]
        self.publications = []

    def load_file(self, file_id):
        return self.evidence

    def matches_file(self, *args):
        return False

    def replace_file(self, *args):
        self.publications.append(args)


class FakeEmbeddings:
    model = "fixture"
    dimensions = 2

    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def embed(self, texts):
        self.calls.append(texts)
        if len(self.calls) == self.fail_at:
            raise RetrievalFailure("embedding_timeout")
        return [(1, 0)] * len(texts)


def test_resumable_cache_and_replay_without_paid_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval_cli, "CACHE", tmp_path)
    index = FakeIndex()
    failing = FakeEmbeddings(fail_at=2)
    with pytest.raises(RetrievalFailure, match="embedding_timeout"):
        retrieval_cli.index_file(index, UUID(int=100), failing)
    assert index.publications == []
    successor = FakeEmbeddings()
    result = retrieval_cli.index_file(index, UUID(int=100), successor)
    assert len(successor.calls) == 1 and len(successor.calls[0]) == 1
    assert result["cache_hits"] == 16 and result["new_embeddings"] == 1
    replay = FakeEmbeddings()
    result = retrieval_cli.index_file(index, UUID(int=100), replay)
    assert replay.calls == [] and result["new_embeddings"] == 0
    assert len(index.publications[-1][1]) == 17
    assert "unique text" not in next(tmp_path.glob("*.json")).read_text()


def test_identical_messages_keep_distinct_evidence_but_embed_once(tmp_path, monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(retrieval_cli, "CACHE", tmp_path)
    index = FakeIndex(2)
    index.evidence[1] = replace(index.evidence[1], text=index.evidence[0].text)
    embedder = FakeEmbeddings()
    result = retrieval_cli.index_file(index, UUID(int=100), embedder)
    assert result["documents"] == 2 and result["unique_messages"] == 1
    assert len(embedder.calls[0]) == 1
    assert len(index.publications[-1][2]) == 2


def test_current_database_snapshot_skips_cache_and_api(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval_cli, "CACHE", tmp_path)
    index = FakeIndex(2)
    index.matches_file = lambda *args: True
    embedder = FakeEmbeddings(fail_at=1)
    result = retrieval_cli.index_file(index, UUID(int=100), embedder)
    assert result["index_unchanged"] and result["new_embeddings"] == 0
    assert embedder.calls == [] and index.publications == []
    assert list(tmp_path.iterdir()) == []
