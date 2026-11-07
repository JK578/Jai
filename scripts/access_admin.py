"""Local operator provisioning; credentials are written only to ignored local files."""

import argparse
import hashlib
import json
import secrets
import ssl
import time
from pathlib import Path
from uuid import UUID, uuid4

import certifi
import httpx
from dotenv import set_key
from incidentiq.config import ENV_FILE, load_settings
from incidentiq.infrastructure.database import Database, database_engine
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

from scripts.manage_database import verify_schema
from scripts.retrieval_cli import ROOT, save

PRIVATE = ROOT / ".cache/access"
SCOPES = [
    "search:run",
    "incidents:read",
    "incidents:write",
    "logs:read",
    "investigations:read",
    "investigations:write",
    "investigations:approve",
]


def issue(tenant_id, read_only=False):
    token = secrets.token_urlsafe(40)
    user_id = uuid4()
    path = PRIVATE / "tokens.json"
    entries = json.loads(path.read_text()) if path.exists() else []
    if len(entries) >= 100:
        raise ValueError("Review token retention before adding more users")
    entries.append(
        {
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": int(time.time()) + 86400,
            "scopes": ["incidents:read", "logs:read", "investigations:read"]
            if read_only
            else SCOPES,
        }
    )
    PRIVATE.mkdir(parents=True, exist_ok=True)
    save(path, entries)
    (PRIVATE / "login.txt").write_text(token + "\n", encoding="utf-8")
    return {
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "expires_in_hours": 24,
        "login_file": ".cache/access/login.txt",
    }


def bootstrap():
    if (PRIVATE / "tokens.json").exists():
        raise ValueError("Already provisioned; use issue/revoke")
    settings = load_settings()
    if settings.environment != "development" or settings.database_url is None:
        raise ValueError("Development owner connection required")
    engine = database_engine(settings.database_url, pooled=False)
    password, tenant_id = secrets.token_urlsafe(48), uuid4()
    username = "incidentiq_app"
    owner_url = engine.url
    if "." in owner_url.username:
        username += "." + owner_url.username.split(".", 1)[1]
    PRIVATE.mkdir(parents=True, exist_ok=True)
    ca = PRIVATE / "ca-bundle.pem"
    if not ca.exists():
        with httpx.Client(timeout=10, follow_redirects=True, trust_env=False) as client:
            response = client.get(
                "https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/"
                "prod/ssl/prod-ca-2021.crt"
            )
            response.raise_for_status()
            pem = response.text
            if len(pem) > 65536:
                raise ValueError("Unexpected CA size")
            ssl.PEM_cert_to_DER_cert(pem)
            ca.write_text(Path(certifi.where()).read_text() + "\n" + pem, encoding="utf-8")
    pending = PRIVATE / "runtime-url.pending"
    if pending.exists():
        runtime_url = make_url(pending.read_text())
        if runtime_url.host != owner_url.host or runtime_url.username != username:
            raise ValueError("Unexpected pending runtime target")
        password = runtime_url.password
    else:
        runtime_url = owner_url.set(username=username, password=password)
    runtime_url = runtime_url.update_query_dict({"sslmode": "verify-full", "sslrootcert": str(ca)})
    # Recovery copy exists before database commit; never print the connection string.
    (PRIVATE / "runtime-url.pending").write_text(
        runtime_url.render_as_string(hide_password=False), encoding="utf-8"
    )
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout='15000ms'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(1938461)"))
            verify_schema(connection, "0004_access")
            exists = connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='incidentiq_app')")
            )
            if exists:
                tenants = connection.scalars(
                    text("SELECT DISTINCT tenant_id FROM incidentiq.resource_owners")
                ).all()
                if len(tenants) != 1:
                    raise ValueError("Unexpected provisioned ownership")
                tenant_id = tenants[0]
            else:
                statement = (
                    sql.SQL("""CREATE ROLE incidentiq_app LOGIN NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}
                    IN ROLE incidentiq_runtime""")
                    .format(sql.Literal(password))
                    .as_string()
                )
                connection.exec_driver_sql(statement)
                for kind, table in (("incident", "incidents"), ("file", "log_files")):
                    connection.execute(
                        text(f"""INSERT INTO incidentiq.resource_owners
                        SELECT :kind, id, :tenant FROM incidentiq.{table}"""),
                        {"kind": kind, "tenant": tenant_id},
                    )
        runtime = Database(SecretStr(runtime_url.render_as_string(hide_password=False)))
        try:
            if not runtime.restricted() or not runtime.ready():
                raise ValueError("Restricted connection verification failed")
        finally:
            runtime.close()
        set_key(ENV_FILE, "DATABASE_RUNTIME_URL", runtime_url.render_as_string(hide_password=False))
        set_key(ENV_FILE, "INCIDENTIQ_TOKEN_REGISTRY", str(PRIVATE / "tokens.json"))
        set_key(ENV_FILE, "INCIDENTIQ_AUTH_ENABLED", "true")
        set_key(ROOT / "apps/web/.env.local", "INCIDENTIQ_AUTH_ENABLED", "true")
        return {
            **issue(tenant_id),
            "restricted_runtime_verified": True,
            "ssl_policy": "verify-full",
            "auth_enabled": True,
        }
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("bootstrap", "issue", "revoke"))
    parser.add_argument("--tenant-id")
    parser.add_argument("--user-id")
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    if args.operation == "bootstrap":
        result = bootstrap()
        save(
            ROOT / "docs/access-provisioning.json",
            {key: value for key, value in result.items() if key != "login_file"},
        )
    elif args.operation == "issue":
        result = issue(UUID(args.tenant_id), args.read_only)
    else:
        path = PRIVATE / "tokens.json"
        entries = json.loads(path.read_text())
        identity = str(UUID(args.user_id))
        for entry in entries:
            if entry["user_id"] == identity:
                entry["revoked"] = True
        save(path, entries)
        result = {"revoked": identity}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        print("Access provisioning stopped:", type(error).__name__)
        for frame in traceback.extract_tb(error.__traceback__):
            if frame.name in ("bootstrap", "issue", "main"):
                print(frame.name, frame.lineno)
        raise SystemExit(1) from None
