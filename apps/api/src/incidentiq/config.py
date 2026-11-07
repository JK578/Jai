"""Small, validated environment configuration; no external services required."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, model_validator

ENV_FILE = Path(__file__).resolve().parents[2] / "api.env"


class Settings(BaseModel):
    environment: Literal["development", "test", "production"] = "development"
    ready: bool = True
    storage: Literal["auto", "memory", "postgres"] = "auto"
    database_url: SecretStr | None = Field(default=None, repr=False, exclude=True)
    runtime_database_url: SecretStr | None = Field(default=None, repr=False, exclude=True)
    auth_enabled: bool = False
    token_registry: Path = Path(".cache/access/tokens.json")
    data_dir: Path = Path(__file__).resolve().parents[4] / ".cache"

    @model_validator(mode="after")
    def validate_storage(self) -> Settings:
        if self.storage == "postgres" and self.database_url is None:
            raise ValueError("PostgreSQL storage requires DATABASE_URL")
        if self.environment == "production" and not self.auth_enabled:
            raise ValueError("Production requires authentication")
        if self.auth_enabled and self.persistent and self.runtime_database_url is None:
            raise ValueError("Authenticated PostgreSQL requires a restricted runtime URL")
        return self

    @property
    def persistent(self) -> bool:
        return self.storage == "postgres" or (
            self.storage == "auto" and self.database_url is not None
        )


def load_settings() -> Settings:
    load_dotenv(ENV_FILE, override=False)
    raw_url = os.getenv("DATABASE_URL")
    runtime_url = os.getenv("DATABASE_RUNTIME_URL")
    return Settings.model_validate(
        {
            "environment": os.getenv("INCIDENTIQ_ENV", "development"),
            "ready": os.getenv("INCIDENTIQ_READY", "true"),
            "storage": os.getenv("INCIDENTIQ_STORAGE", "auto"),
            "database_url": SecretStr(raw_url) if raw_url else None,
            "runtime_database_url": SecretStr(runtime_url) if runtime_url else None,
            "auth_enabled": os.getenv("INCIDENTIQ_AUTH_ENABLED", "false"),
            "token_registry": os.getenv("INCIDENTIQ_TOKEN_REGISTRY", ".cache/access/tokens.json"),
            "data_dir": os.getenv(
                "INCIDENTIQ_DATA_DIR", str(Path(__file__).resolve().parents[4] / ".cache")
            ),
        }
    )
