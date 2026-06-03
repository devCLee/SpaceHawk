"""Application settings, loaded from the environment.

Defaults are safe for local development; production/enclave values are supplied via
environment variables (12-factor). No secrets are hard-coded.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORBITAL_ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SpaceHawk Orbital Engine"
    version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"

    # JSON logs in shared/production environments; console-friendly locally.
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_json: bool = False

    # Web/BFF origin allowed to call the internal API (the Next.js tier).
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # Connection strings (overridden by env in compose/enclave).
    database_url: str = "postgresql+psycopg://spacehawk:spacehawk@localhost:5432/spacehawk"
    redis_url: str = "redis://localhost:6379/0"


def get_settings() -> Settings:
    """Return application settings (call site can be overridden in tests via DI)."""
    return Settings()
