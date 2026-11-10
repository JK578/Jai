"""Rebase copied server configuration locally; never change database roles or passwords."""

from pathlib import Path

from dotenv import dotenv_values, set_key
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def configure(root=ROOT):
    api = root / "apps/api/api.env"
    values = dotenv_values(api)
    raw = values.get("DATABASE_RUNTIME_URL")
    if not values.get("DATABASE_URL") or not raw:
        raise ValueError(
            "Configure the private owner and restricted runtime URLs in apps/api/api.env first."
        )
    try:
        runtime = make_url(raw)
    except Exception:
        raise ValueError(
            "Invalid restricted runtime URL; check the private api.env file."
        ) from None
    if runtime.query.get("sslmode") != "verify-full":
        raise ValueError("The restricted runtime URL must use sslmode=verify-full.")
    local = root / ".cache/access"
    ca = local / "ca-bundle.pem"
    old_ca = runtime.query.get("sslrootcert")
    if ca.is_file():
        runtime = runtime.update_query_dict({"sslrootcert": str(ca.resolve())})
    elif old_ca:
        raise ValueError(
            "Copy the trusted .cache/access/ca-bundle.pem from the existing environment first."
        )
    local.mkdir(parents=True, exist_ok=True)
    updates = {
        "DATABASE_RUNTIME_URL": runtime.render_as_string(hide_password=False),
        "INCIDENTIQ_ENV": "development",
        "INCIDENTIQ_STORAGE": "postgres",
        "INCIDENTIQ_AUTH_ENABLED": "true",
        "INCIDENTIQ_TOKEN_REGISTRY": str((local / "tokens.json").resolve()),
        "INCIDENTIQ_DATA_DIR": str((root / ".cache").resolve()),
    }
    for key, value in updates.items():
        set_key(api, key, value)
    web = root / "apps/web/.env.local"
    set_key(web, "BACKEND_URL", "http://127.0.0.1:8000")
    set_key(web, "INCIDENTIQ_AUTH_ENABLED", "true")
    return {
        "configuration_rebased": True,
        "database_credentials_rotated": False,
        "database_migrations_applied": False,
    }


if __name__ == "__main__":
    import json

    try:
        print(json.dumps(configure()))
    except ValueError as error:
        print(str(error))
        raise SystemExit(1) from None
    except Exception:
        print("Local configuration failed; sensitive details suppressed.")
        raise SystemExit(1) from None
