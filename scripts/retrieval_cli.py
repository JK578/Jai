"""Explicit bounded indexing/search CLI with digest-only resumable embedding cache."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from incidentiq.config import load_settings
from incidentiq.domain.retrieval import RetrievalFailure, normalized
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.embedding_provider import OpenAIEmbeddingProvider
from incidentiq.infrastructure.log_source import manifest
from incidentiq.infrastructure.retrieval_postgres import PostgresRetrievalIndex
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from scripts.phase2b_live_drill import memory

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/retrieval"


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def open_index():
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise ValueError("development_database_required")
    engine = database_engine(settings.database_url, pooled=False)
    with engine.connect() as connection:
        if connection.scalar(
            text("SELECT version_num FROM public.incidentiq_alembic_version")
        ) not in {"0003_retrieval", "0004_access"}:
            engine.dispose()
            raise ValueError("retrieval_migration_required")
    return engine, PostgresRetrievalIndex(sessionmaker(engine, expire_on_commit=False))


def provider(budget: int):
    return OpenAIEmbeddingProvider(SecretStr(os.environ.get("OPENAI_API_KEY", "")), budget)


def index_file(index, file_id, embedder, progress=lambda done, total: None):
    evidence = index.load_file(file_id)
    digest_map = {hashlib.sha256(item.text.encode()).hexdigest(): item.text for item in evidence}
    if index.matches_file(file_id, evidence, embedder.model, embedder.dimensions):
        return {
            "documents": len(evidence),
            "unique_messages": len(digest_map),
            "new_embeddings": 0,
            "cache_hits": 0,
            "index_unchanged": True,
        }
    # Only hashes and vectors are cached; no raw messages or credentials.
    path = CACHE / f"{file_id}-{embedder.model}-{embedder.dimensions}.json"
    cached = json.loads(path.read_text()) if path.exists() else {}
    vectors = {
        digest: normalized(tuple(vector), embedder.dimensions)
        for digest, vector in cached.items()
        if digest in digest_map
    }
    missing = [digest for digest in digest_map if digest not in vectors]
    for offset in range(0, len(missing), 16):
        batch = missing[offset : offset + 16]
        result = embedder.embed([digest_map[digest] for digest in batch])
        if len(result) != len(batch):
            raise RetrievalFailure("embedding_invalid")
        vectors.update(
            {
                digest: normalized(vector, embedder.dimensions)
                for digest, vector in zip(batch, result, strict=True)
            }
        )
        save(path, vectors)
        progress(min(offset + 16, len(missing)), len(missing))
    ordered = [vectors[hashlib.sha256(item.text.encode()).hexdigest()] for item in evidence]
    index.replace_file(file_id, evidence, ordered, embedder.model, embedder.dimensions)
    return {
        "documents": len(evidence),
        "unique_messages": len(digest_map),
        "new_embeddings": len(missing),
        "cache_hits": len(digest_map) - len(missing),
        "index_unchanged": False,
    }


def status(engine, file_id):
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = connection.execute(
            text("""SELECT event_id::text, model, dimensions,
            content_sha256, embedding::text FROM incidentiq.retrieval_documents
            WHERE file_id=:id ORDER BY event_id""").execution_options(stream_results=True),
            {"id": file_id},
        )
        digest = hashlib.sha256()
        count = 0
        for row in rows:
            digest.update(json.dumps(list(row)).encode())
            digest.update(b"\n")
            count += 1
        fingerprint = digest.hexdigest()
        storage = connection.scalar(
            text("SELECT pg_total_relation_size('incidentiq.retrieval_documents')")
        )
        events = connection.scalar(text("SELECT count(*) FROM incidentiq.log_events"))
        return {
            "documents": count,
            "index_sha256": fingerprint,
            "retrieval_storage_bytes": storage,
            "source_events": events,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("index", "status", "search"))
    parser.add_argument("--budget-microusd", type=int, default=100000)
    parser.add_argument("--query", default="")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    engine, index = open_index()
    try:
        file_id = manifest().file_id
        if args.operation == "status":
            result = status(engine, file_id)
        elif args.operation == "index":
            embedder = provider(args.budget_microusd)
            before = status(engine, file_id)
            baseline = memory()
            result = index_file(
                index,
                file_id,
                embedder,
                lambda done, total: print(f"Embedded unique messages: {done}/{total}", flush=True),
            )
            after = status(engine, file_id)
            after_memory = memory()
            result.update(
                {
                    "before": before,
                    "after": after,
                    "budget_microusd": args.budget_microusd,
                    "conservative_spent_microusd": args.budget_microusd
                    - embedder.remaining_microusd,
                    "worker_peak_bytes": after_memory["peak_working_set_bytes"],
                    "worker_peak_minus_baseline_bytes": max(
                        0, after_memory["peak_working_set_bytes"] - baseline["working_set_bytes"]
                    ),
                }
            )
        else:
            if not args.query.strip() or len(args.query.encode()) > 800:
                raise ValueError("search_bounds_invalid")
            embedder = provider(args.budget_microusd)
            vector = embedder.embed([args.query])[0]
            hits = index.search(file_id, args.query, vector, embedder.model, embedder.dimensions, 5)
            result = {
                "hits": [
                    {
                        "event_id": str(hit.evidence.event_id),
                        "source_line": hit.evidence.source_line,
                        "source_path": hit.evidence.source_path,
                        "source_commit": hit.evidence.source_commit,
                        "file_sha256": hit.evidence.file_sha256,
                        "text": hit.evidence.text,
                        "score": hit.score,
                    }
                    for hit in hits
                ]
            }
        if args.receipt:
            save(args.receipt, result)
        print(json.dumps(result, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (RetrievalFailure, ValueError) as error:
        print(str(error) if isinstance(error, RetrievalFailure) else "retrieval_input_invalid")
        raise SystemExit(1) from None
    except Exception:
        print("retrieval_cli_unavailable; details suppressed")
        raise SystemExit(1) from None
