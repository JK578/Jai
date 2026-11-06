"""Metadata-only migration safety helpers."""

import hashlib
import json

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


class SchemaSafetyStop(RuntimeError):
    pass


def unrelated_fingerprint(connection: Connection) -> tuple[str, int]:
    # Metadata only, never table contents. Capture columns, defaults, constraints, indexes and ACLs.
    rows = connection.execute(
        text("""
        SELECT n.nspname, c.relname, c.relkind, c.relrowsecurity, c.relacl::text,
          (SELECT string_agg(a.attname || ':' || a.atttypid::text || ':' || a.atttypmod::text
             || ':' || a.attnotnull::text || ':' || coalesce(pg_get_expr(d.adbin,d.adrelid),''),
             ',' ORDER BY a.attnum)
           FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
           WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
          (SELECT string_agg(pg_get_constraintdef(k.oid),',' ORDER BY k.conname)
           FROM pg_constraint k WHERE k.conrelid=c.oid),
          (SELECT string_agg(indexdef,',' ORDER BY indexname) FROM pg_indexes i
           WHERE i.schemaname=n.nspname AND i.tablename=c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname NOT IN ('information_schema','incidentiq')
          AND NOT (n.nspname='public' AND c.relname LIKE 'incidentiq_alembic_version%')
        ORDER BY n.nspname,c.relname
    """)
    ).all()
    serialized = json.dumps([list(row) for row in rows], default=str, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest(), len(rows)


def pristine(connection: Connection) -> None:
    inspector = inspect(connection)
    if "incidentiq" in inspector.get_schema_names():
        raise SchemaSafetyStop("Unexpected existing incidentiq schema; stopped without migration")
    if inspector.has_table("incidentiq_alembic_version", schema="public"):
        raise SchemaSafetyStop("Existing migration tracking state; initial-only guard stopped")
    if inspector.has_table("incidents", schema="public"):
        raise SchemaSafetyStop("Unexpected public.incidents table; stopped for schema review")
