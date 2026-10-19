"""Small, validated environment configuration; no external services required."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    environment: Literal["development", "test", "production"] = "development"
    ready: bool = True


def load_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return Settings.model_validate(
        {
            "environment": os.getenv("INCIDENTIQ_ENV", "development"),
            "ready": os.getenv("INCIDENTIQ_READY", "true"),
        }
    )
