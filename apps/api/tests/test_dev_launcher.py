import socket

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from scripts import configure_local, dev


def test_default_setup_preserves_existing_private_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    for directory, filename in (("api", "api.env"), ("web", ".env.local")):
        path = tmp_path / "apps" / directory
        path.mkdir(parents=True)
        (path / ".env.example").write_text("example")
        (path / filename).write_text("private existing settings")
    dev.copy_defaults()
    assert (tmp_path / "apps/api/api.env").read_text() == "private existing settings"
    assert (tmp_path / "apps/web/.env.local").read_text() == "private existing settings"


def test_ports_fail_without_stopping_existing_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(ValueError, match="busy"):
            dev.available(listener.getsockname()[1])
        assert listener.fileno() != -1


def test_rebase_preserves_database_credentials_and_enforces_tls(tmp_path):
    api = tmp_path / "apps/api"
    web = tmp_path / "apps/web"
    private = tmp_path / ".cache/access"
    for path in (api, web, private):
        path.mkdir(parents=True)
    (private / "ca-bundle.pem").write_text("trusted test fixture")
    owner = "postgresql+psycopg://owner:password@localhost/database"
    runtime = (
        "postgresql+psycopg://runtime:password@localhost/database"
        "?sslmode=verify-full&sslrootcert=C:/old/ca.pem"
    )
    (api / "api.env").write_text(f"DATABASE_URL='{owner}'\nDATABASE_RUNTIME_URL='{runtime}'\n")
    result = configure_local.configure(tmp_path)
    values = dotenv_values(api / "api.env")
    assert values["DATABASE_URL"] == owner
    parsed = make_url(values["DATABASE_RUNTIME_URL"])
    assert parsed.password == "password" and parsed.username == "runtime"
    assert parsed.query["sslmode"] == "verify-full"
    assert parsed.query["sslrootcert"] == str((private / "ca-bundle.pem").resolve())
    assert values["INCIDENTIQ_TOKEN_REGISTRY"] == str((private / "tokens.json").resolve())
    assert result["database_migrations_applied"] is False
    insecure = runtime.replace("verify-full", "require")
    (api / "api.env").write_text(f"DATABASE_URL='{owner}'\nDATABASE_RUNTIME_URL='{insecure}'\n")
    with pytest.raises(ValueError, match="verify-full"):
        configure_local.configure(tmp_path)
    (api / "api.env").write_text(
        f"DATABASE_URL='{owner}'\nDATABASE_RUNTIME_URL='private invalid value'\n"
    )
    with pytest.raises(ValueError, match="Invalid restricted runtime URL") as error:
        configure_local.configure(tmp_path)
    assert "private invalid value" not in str(error.value)
