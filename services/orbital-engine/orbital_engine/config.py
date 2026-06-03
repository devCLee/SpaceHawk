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

    # --- Source credentials (Stage 2) ---
    # Presence of these gates SourceAdapter.available(): unset => the scheduler
    # skips the source. None in dev/air-gap until each feed's agreement lands.
    discos_api_token: str | None = None
    leolabs_api_key: str | None = None
    leolabs_api_secret: str | None = None

    # --- Space-Track (authoritative primary source) ---
    # In the enclave the base URL points at the cross-domain mirror, not the
    # public site (air-gap §4.6). Identity/password unset => adapter unavailable.
    spacetrack_base_url: str = "https://www.space-track.org"
    spacetrack_identity: str | None = None
    spacetrack_password: str | None = None
    # Stay under Space-Track's published 30 req/min ceiling.
    spacetrack_max_requests_per_min: int = 20
    # Cap per-query rows in dev; None (no limit) for the full catalog in the enclave.
    spacetrack_query_limit: int | None = None

    # --- Scheduler (Celery + Redis broker; see docs/DECISIONS.md) ---
    # Default the broker/backend to the same Redis as hot state; override per-env.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    # Per-source ingest cadence (seconds). Space-Track hourly (rate-limited,
    # authoritative); Celestrak more frequent (redundant/low-latency).
    spacetrack_ingest_interval_sec: int = 3600
    celestrak_ingest_interval_sec: int = 1800

    # --- Stage 1 thin-slice knobs ---
    # Single Celestrak GP group is the slice's one source (see P0-THIN-SLICE-PLAN).
    # In the air-gapped enclave this is pointed at the offline mirror instead.
    celestrak_gp_url: str = "https://celestrak.org/NORAD/elements/gp.php"
    celestrak_group: str = "active"
    # Cap ingested objects for the spike: keep the catalog small enough to render
    # with the (pre-migration) Entity path and to propagate every tick cheaply.
    ingest_limit: int = 200
    # How often the background loop re-propagates the set and refreshes Redis.
    propagation_interval_sec: int = 5
    # TTL on per-object latest-state keys; a few propagation cycles, so a stalled
    # loop lets state expire instead of serving silently-stale positions.
    state_ttl_sec: int = 60
    # Trivial rule-based alert: object inside this lat/lon box (Korean theatre).
    roi_lat_min: float = 33.0
    roi_lat_max: float = 43.0
    roi_lon_min: float = 124.0
    roi_lon_max: float = 132.0


def get_settings() -> Settings:
    """Return application settings (call site can be overridden in tests via DI)."""
    return Settings()
