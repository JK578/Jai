"""Reproducible offline ranking evaluation on synthetic evidence and curated vectors."""

import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from incidentiq.application.retrieval import RetrievalService
from incidentiq.domain.retrieval import Evidence
from incidentiq.infrastructure.retrieval_memory import InMemoryRetrievalIndex

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "apps/api/tests/fixtures/retrieval.json"


def evaluate() -> dict:
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    file_id = uuid5(NAMESPACE_URL, digest)
    vectors = {
        item["text"]: tuple(item["vector"]) for item in fixture["documents"] + fixture["queries"]
    }

    class CuratedEmbeddings:
        model = "curated-fixture-v1"
        dimensions = 3

        def embed(self, texts):
            return [vectors[text] for text in texts]

    service = RetrievalService(CuratedEmbeddings(), InMemoryRetrievalIndex())
    corpus = [
        Evidence(
            uuid5(file_id, str(item["line"])),
            file_id,
            item["line"],
            "tests/fixtures/retrieval.json",
            "0" * 40,
            digest,
            item["text"],
        )
        for item in fixture["documents"]
    ]
    service.index_file(file_id, corpus)
    records = []
    totals = {mode: {"recall_at_1": 0.0, "mrr": 0.0} for mode in ("keyword", "vector", "hybrid")}
    for query in fixture["queries"]:
        hits = service.search(file_id, query["text"], limit=20)
        rankings = {
            "hybrid": [hit.evidence.source_line for hit in hits],
            "keyword": [
                hit.evidence.source_line
                for hit in sorted(
                    (h for h in hits if h.keyword_rank is not None), key=lambda h: h.keyword_rank
                )
            ],
            "vector": [
                hit.evidence.source_line
                for hit in sorted(
                    (h for h in hits if h.vector_rank is not None), key=lambda h: h.vector_rank
                )
            ],
        }
        relevant = set(query["relevant_lines"])
        for mode, lines in rankings.items():
            totals[mode]["recall_at_1"] += len(set(lines[:1]) & relevant) / len(relevant)
            totals[mode]["mrr"] += next(
                (1 / rank for rank, line in enumerate(lines, 1) if line in relevant), 0
            )
        records.append(
            {"query": query["text"], "relevant_lines": sorted(relevant), "ranked_lines": rankings}
        )
    for metrics in totals.values():
        for name in metrics:
            metrics[name] = round(metrics[name] / len(fixture["queries"]), 6)
    service.delete_file(file_id)
    return {
        "fixture_sha256": digest,
        "embedding_model": "curated-fixture-v1",
        "scope": "Controlled ranking mechanics only; not semantic model quality.",
        "documents": len(corpus),
        "queries": len(records),
        "metrics": totals,
        "results": records,
        "deletion_verified": service.search(file_id, "restart") == [],
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
