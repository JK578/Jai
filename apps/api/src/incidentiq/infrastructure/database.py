"""Bounded PostgreSQL resources. Construction never connects or mutates schema."""

import logging

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from incidentiq.infrastructure.models import IncidentRow


def database_engine(secret: SecretStr, *, pooled: bool = True) -> Engine:
    from sqlalchemy.pool import NullPool

    try:
        url = make_url(secret.get_secret_value())
        if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
            raise ValueError
        if not all((url.host, url.username, url.password, url.database)):
            raise ValueError
        mode = url.query.get("sslmode", "require")
        if mode not in ("require", "verify-ca", "verify-full"):
            mode = "require"
        arguments = {
            "connect_timeout": 5,
            "sslmode": mode,
            "prepare_threshold": None,
        }
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("psycopg").setLevel(logging.CRITICAL)
        options = (
            {"pool_size": 2, "max_overflow": 0, "pool_timeout": 2}
            if pooled
            else {"poolclass": NullPool}
        )
        return create_engine(
            url.set(drivername="postgresql+psycopg"),
            connect_args=arguments,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False,
            hide_parameters=True,
            **options,
        )
    except Exception:
        raise ValueError(
            "Invalid PostgreSQL configuration; connection details suppressed"
        ) from None


class Database:
    def __init__(self, secret: SecretStr) -> None:
        self.engine = database_engine(secret)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def ready(self) -> bool:
        try:
            with self.sessions() as session:
                self.bound_statement(session)
                # Check the mapped table as well as connectivity; no schema creation here.
                session.execute(select(IncidentRow).limit(0))
            return True
        except SQLAlchemyError:
            return False

    def restricted(self) -> bool:
        from sqlalchemy import text

        try:
            with self.sessions() as session:
                self.bound_statement(session)
                return bool(
                    session.scalar(
                        text("""SELECT NOT (rolsuper OR rolbypassrls OR
                    rolcreaterole OR rolcreatedb OR rolreplication) AND
                    NOT has_schema_privilege(current_user, 'incidentiq', 'CREATE') AND
                    NOT has_schema_privilege(current_user, 'public', 'CREATE') AND
                    NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='incidentiq'
                                AND tableowner=current_user)
                    FROM pg_roles WHERE rolname=current_user""")
                    )
                )
        except SQLAlchemyError:
            return False

    @staticmethod
    def bound_statement(session: Session) -> None:
        from sqlalchemy import text

        session.execute(text("SET LOCAL statement_timeout = '3000ms'"))

    def close(self) -> None:
        self.engine.dispose()
