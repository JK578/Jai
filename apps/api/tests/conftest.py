"""Default tests never read developer credentials or connect to cloud services."""

from pathlib import Path

import pytest
from incidentiq import config


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "api.env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("INCIDENTIQ_STORAGE", raising=False)
