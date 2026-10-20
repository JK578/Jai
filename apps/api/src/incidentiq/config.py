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

    @model_validator(mode="after")
    def validate_storage(self) -> Settings:
        if self.storage == "postgres" and self.database_url is None:
            raise ValueError("PostgreSQL storage requires DATABASE_URL")
        return self

    @property
    def persistent(self) -> bool:
        return self.storage == "postgres" or (
            self.storage == "auto" and self.database_url is not None
        )


def load_settings() -> Settings:
    load_dotenv(ENV_FILE, override=False)
    raw_url = os.getenv("DATABASE_URL")
    return Settings.model_validate(
        {
            "environment": os.getenv("INCIDENTIQ_ENV", "development"),
            "ready": os.getenv("INCIDENTIQ_READY", "true"),
            "storage": os.getenv("INCIDENTIQ_STORAGE", "auto"),
            "database_url": SecretStr(raw_url) if raw_url else None,
        }
    )
