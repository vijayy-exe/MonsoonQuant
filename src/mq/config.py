"""Typed settings for MonsoonQuant. All config flows through here — never read
os.environ directly elsewhere."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://mq:mq@localhost:5433/monsoonquant"

    object_store_backend: str = "local"
    object_store_path: str = "./data/objects"

    mlflow_tracking_uri: str = "http://localhost:5001"

    cds_api_key: str = ""
    cds_api_url: str = "https://cds.climate.copernicus.eu/api"

    api_rate_limit_per_min: int = 60
    api_key_salt: str = ""

    # SPEC §12: "CORS restricted to the web origin" -- defaults to the
    # local Next.js dev server; override via MQ_WEB_ORIGINS (a JSON
    # array, e.g. '["https://example.com"]' -- pydantic-settings' own
    # parsing rule for list-typed env vars) once M14 deploys a real origin.
    web_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    sentry_dsn: str = ""

    ledger_public_repo_url: str = ""

    log_level: str = Field(default="INFO")


def get_settings() -> Settings:
    return Settings()
