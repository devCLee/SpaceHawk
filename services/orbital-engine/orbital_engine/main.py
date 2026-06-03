"""FastAPI application factory for the SpaceHawk Orbital Engine."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orbital_engine.api import health
from orbital_engine.config import Settings, get_settings
from orbital_engine.logging import configure_logging, get_logger


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    log = get_logger("orbital_engine")

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "SpaceHawk Orbital Engine — internal domain/compute API "
            "(ingestion, catalog, propagation, screening, analytics). "
            "Reached only by the web/BFF tier over a private network; never serves HTML."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    log.info("app.startup", environment=settings.environment, version=settings.version)
    return app


app = create_app()
