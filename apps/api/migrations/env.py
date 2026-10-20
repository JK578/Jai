"""Offline generation never reads credentials; online mode requires a reviewed guard."""

from alembic import context
from incidentiq.infrastructure.models import Base

config = context.config
options = {
    "target_metadata": Base.metadata,
    "version_table": "incidentiq_alembic_version",
    "version_table_schema": "public",
    "include_schemas": True,
}

if context.is_offline_mode():
    context.configure(dialect_name="postgresql", literal_binds=True, **options)
else:
    connection = config.attributes.get("connection")
    if connection is None or not config.attributes.get("schema_reviewed"):
        raise RuntimeError("Use scripts/manage_database.py for inspected and reviewed migrations")
    context.configure(connection=connection, **options)

with context.begin_transaction():
    context.run_migrations()
