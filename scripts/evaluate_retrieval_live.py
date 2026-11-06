"""Evaluate fixed source-derived relevance labels against real PostgreSQL retrieval."""

import hashlib
import json
import math
import re
import time

from incidentiq.infrastructure.log_source import manifest

from scripts.retrieval_cli import ROOT, open_index, provider, save, status


def metrics(lines, relevant):
    judged = [line in relevant for line in lines[:5]]
    dcg = sum(1 / math.log2(rank + 1) for rank, yes in enumerate(judged, 1) if yes)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(5, len(relevant)) + 1))
    return {
        "hit_at_5": float(any(judged)),
        "recall_at_5": sum(judged) / len(relevant),
        "mrr_at_5": next((1 / rank for rank, yes in enumerate(judged, 1) if yes), 0),
        "ndcg_at_5": dcg / ideal,
    }


def evaluate():
    label_path = ROOT / "docs/phase4-queries.json"
    label_bytes = label_path.read_bytes()
    labels = json.loads(label_bytes)
    source = manifest()
    assert labels["file_sha256"] == source.sha256
    engine, index = open_index()
    try:
        corpus = index.load_file(source.file_id)
        lookup = {item.event_id: item for item in corpus}
        # All labels resolved from source content before any query vectors or rankings.
        relevance = [
            {item.source_line for item in corpus if re.search(label["relevant_pattern"], item.text)}
            for label in labels["queries"]
        ]
        if not all(relevance):
            raise ValueError("evaluation_label_has_no_evidence")
        embedder = provider(20000)
        query_vectors = embedder.embed([label["query"] for label in labels["queries"]])
        rows = []
        timing = []
        totals = {mode: {} for mode in ("keyword", "vector", "hybrid")}
        for label, relevant, vector in zip(
            labels["queries"], relevance, query_vectors, strict=True
        ):
            result = {
                "query": label["query"],
                "kind": label["kind"],
                "relevant_source_lines": sorted(relevant),
                "modes": {},
            }
            for mode in totals:
                started = time.perf_counter()
                hits = index.search(
                    source.file_id,
                    label["query"],
                    vector,
                    embedder.model,
                    embedder.dimensions,
                    5,
                    mode=mode,
                )
                elapsed = (time.perf_counter() - started) * 1000
                timing.append(elapsed)
                assert all(lookup[hit.evidence.event_id] == hit.evidence for hit in hits)
                lines = [hit.evidence.source_line for hit in hits]
                measured = metrics(lines, relevant)
                for key, value in measured.items():
                    totals[mode][key] = totals[mode].get(key, 0) + value / len(relevance)
                result["modes"][mode] = {
                    "source_lines": lines,
                    "metrics": measured,
                    "elapsed_ms": round(elapsed, 2),
                }
            rows.append(result)
        return {
            "label_sha256": hashlib.sha256(label_bytes).hexdigest(),
            "label_method": labels["label_method"],
            "query_count": len(rows),
            "model": embedder.model,
            "dimensions": embedder.dimensions,
            "reported_embedding_tokens": 20000 - embedder.remaining_microusd,
            "estimated_embedding_usd_at_0_02_per_million": (20000 - embedder.remaining_microusd)
            * 0.02
            / 1000000,
            "citation_checks_passed": True,
            "index": status(engine, source.file_id),
            "aggregate_metrics": totals,
            "maximum_observed_query_ms": round(max(timing), 2),
            "results": rows,
        }
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        result = evaluate()
        save(ROOT / "docs/phase4-live-evaluation.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    except Exception:
        print("live_retrieval_evaluation_failed; details suppressed")
        raise SystemExit(1) from None
