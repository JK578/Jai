"""Read-only connection probe. Never display URLs or raw database exceptions."""

import logging
import os
import platform
import socket
from importlib.metadata import version

from dotenv import dotenv_values
from incidentiq.config import ENV_FILE, load_settings


def failure_category(error: Exception) -> str:
    # Inspect internally; only fixed, non-sensitive labels may leave this function.
    message = str(error).lower()
    if any(word in message for word in ("10013", "permission denied", "forbidden")):
        return "network access denied"
    if any(
        word in message
        for word in ("translate host", "getaddrinfo", "name or service", "no such host")
    ):
        return "DNS resolution failed"
    if any(word in message for word in ("password authentication", "tenant or user not found")):
        return "authentication failed"
    if any(word in message for word in ("ssl", "certificate", "tls")):
        return "SSL negotiation or certificate verification failed"
    if "timeout" in message or "timed out" in message:
        return "connection timed out"
    return "connection failed; credentials and diagnostic details suppressed"


def verify() -> int:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    for name in ("sqlalchemy", "psycopg", "dotenv"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    print(f"Python: {platform.python_version()}")
    print(f"Dependencies: SQLAlchemy {version('sqlalchemy')}, psycopg {version('psycopg')}")
    configured = dotenv_values(ENV_FILE).get("DATABASE_URL")
    load_settings()  # Exercise the application's existing dotenv loading path.
    raw = os.environ.get("DATABASE_URL")
    if not raw or not raw.strip():
        print("DATABASE_URL loading: FAIL (missing or empty)")
        return 1
    if configured and raw != configured:
        print("DATABASE_URL loading: FAIL (environment overrides api.env; ambiguous target)")
        return 1
    print("DATABASE_URL loading: PASS (value withheld)")
    url = make_url(raw)
    if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
        print("PostgreSQL URL validation: FAIL (unsupported driver)")
        return 1
    if not url.host or not url.username or not url.password or not url.database:
        print("PostgreSQL URL validation: FAIL (required connection fields missing)")
        return 1
    print("PostgreSQL URL validation: PASS (connection fields withheld)")
    sslmode = url.query.get("sslmode", "require")
    if sslmode not in ("require", "verify-ca", "verify-full"):
        sslmode = "require"
    engine = create_engine(
        url.set(drivername="postgresql+psycopg"),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "sslmode": sslmode, "prepare_threshold": None},
        execution_options={"postgresql_readonly": True},
    )
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            print("SELECT 1: PASS")
            driver = connection.connection.driver_connection
            encrypted = bool(driver.pgconn.ssl_in_use)
            print(f"SSL client connection: {'PASS' if encrypted else 'FAIL'}")
            print(f"SSL policy: {sslmode} (probe only; api.env unchanged)")
            print("Python 3.15 driver execution: PASS")
            connection.rollback()
            return 0 if encrypted else 1
    except Exception as error:
        category = failure_category(error)
        print(f"SELECT 1: FAIL ({category})")
        if category == "DNS resolution failed":
            host = url.host or ""
            if any(character in host for character in ("@", "/", " ", "[", "]")):
                print("Hostname validation: FAIL (unexpected delimiter; check URL encoding)")
            else:
                kind = (
                    "Supabase direct"
                    if host.endswith(".supabase.co")
                    else ("Supabase pooler" if host.endswith(".pooler.supabase.com") else "other")
                )
                print(f"Endpoint category: {kind} (hostname withheld)")
                for label, family in (("IPv4", socket.AF_INET), ("IPv6", socket.AF_INET6)):
                    try:
                        socket.getaddrinfo(host, url.port or 5432, family, socket.SOCK_STREAM)
                        print(f"{label} DNS: PASS")
                    except OSError:
                        print(f"{label} DNS: FAIL (no address resolved)")
        print("SSL client connection: FAIL (not verified; no successful connection)")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(verify())
    except Exception:
        # Do not let config/URL parse failures generate a traceback containing input.
        print("Verification: FAIL (configuration or dependency error; details suppressed)")
        raise SystemExit(1) from None
