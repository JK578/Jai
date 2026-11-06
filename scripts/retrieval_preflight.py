"""Read-only development database capability/headroom probe; never enables extensions."""

import json

from incidentiq.config import load_settings
from incidentiq.infrastructure.database import database_engine
from sqlalchemy import text


def probe() -> dict:
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise ValueError("development_database_required")
    engine = database_engine(settings.database_url, pooled=False)
    try:
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout='5000ms'"))
                installed = connection.execute(
                    text("""SELECT e.extversion, n.nspname
                    FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
                    WHERE e.extname='vector'""")
                ).first()
                available = connection.scalar(
                    text("SELECT default_version FROM pg_available_extensions WHERE name='vector'")
                )
                extensions_schema = connection.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='extensions')")
                )
                size = connection.scalar(text("SELECT pg_database_size(current_database())"))
                revision = connection.scalar(
                    text("SELECT version_num FROM public.incidentiq_alembic_version")
                )
                indexed = (
                    connection.scalar(text("SELECT count(*) FROM incidentiq.retrieval_documents"))
                    if revision == "0003_retrieval"
                    else None
                )
                count = connection.scalar(text("SELECT count(*) FROM incidentiq.log_events"))
                too_long = connection.scalar(
                    text("""SELECT count(*) FROM incidentiq.log_events
                    WHERE octet_length(message)>8000 OR btrim(message)=''""")
                )
                return {
                    "read_only": True,
                    "extensions_schema_exists": extensions_schema,
                    "revision": revision,
                    "retrieval_documents": indexed,
                    "vector_available_version": available,
                    "vector_installed_version": installed[0] if installed else None,
                    "vector_schema": installed[1] if installed else None,
                    "database_bytes": size,
                    "headroom_below_400mib": 400 * 1024**2 - size,
                    "log_events": count,
                    "events_requiring_chunking": too_long,
                }
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(probe(), indent=2))
    except Exception:
        print("retrieval_preflight_unavailable; connection details suppressed")
        raise SystemExit(1) from None
