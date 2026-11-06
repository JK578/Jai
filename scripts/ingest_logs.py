"""Explicit development-only ingestion. Never invoked by the API or migrations."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from incidentiq.application.log_ingestion import ingest
from incidentiq.config import load_settings
from incidentiq.domain.logs import LogError
from incidentiq.infrastructure.database import database_engine
from incidentiq.infrastructure.log_repository import PostgresLogRepository
from incidentiq.infrastructure.log_source import fetch, manifest
from sqlalchemy.orm import sessionmaker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["fetch", "ingest"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--resume", type=UUID)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--allow-development-ingestion", action="store_true")
    args = parser.parse_args()
    if args.operation == "fetch":
        path = fetch(Path(__file__).resolve().parents[1] / ".cache/loghub")
        print(f"PASS: pinned artifact verified; cached as {path.name}")
        return
    settings = load_settings()
    if (
        not args.allow_development_ingestion
        or settings.environment != "development"
        or not settings.persistent
        or settings.database_url is None
        or args.source is None
    ):
        raise LogError("explicit_development_ingestion_and_source_required")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        result = asdict(
            ingest(
                PostgresLogRepository(sessionmaker(engine, expire_on_commit=False)),
                args.source,
                manifest(),
                batch_size=args.batch_size,
                resume=args.resume,
            )
        )
        result.pop("owner_token")
        print(json.dumps(result, default=str, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except LogError:
        print("STOP: ingestion failed; inspect read-only run status for bounded diagnostics")
        raise SystemExit(1) from None
    except Exception:
        print("STOP: operation failed; credentials and internal details suppressed")
        raise SystemExit(1) from None
