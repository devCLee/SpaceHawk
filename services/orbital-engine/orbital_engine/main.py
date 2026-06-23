"""FastAPI application factory for the SpaceHawk Orbital Engine."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orbital_engine.api import audit, auth, catalog, conjunctions, debris, health, maneuvers
from orbital_engine.config import Settings, get_settings
from orbital_engine.db import dispose
from orbital_engine.logging import configure_logging, get_logger
from orbital_engine.pipeline import (
    ingest_if_empty,
    run_fingerprint_loop,
    run_ingest_loop,
    run_maneuver_loop,
    run_propagation_loop,
    run_rpo_loop,
    run_screening_loop,
)
from orbital_engine.reports import router as reports
from orbital_engine.seed_maneuver import seed_demo_maneuver
from orbital_engine.state import close as close_redis


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.assert_secure_for_environment()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    log = get_logger("orbital_engine")

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Boot the thin-slice data plane: ingest-on-empty, then the propagation
        # loop. Failures here (e.g. DB not up yet) must not block serving HTTP —
        # the loop retries each tick and readiness reflects dependency health.
        stop = asyncio.Event()
        try:
            await ingest_if_empty(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("startup.ingest_failed", error=str(exc))
        try:
            await seed_demo_maneuver(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("startup.seed_maneuver_failed", error=str(exc))
        tasks = [
            asyncio.create_task(run_ingest_loop(settings, stop)),
            asyncio.create_task(run_propagation_loop(settings, stop)),
            asyncio.create_task(run_screening_loop(settings, stop)),
            asyncio.create_task(run_maneuver_loop(settings, stop)),
            asyncio.create_task(run_rpo_loop(settings, stop)),
            asyncio.create_task(run_fingerprint_loop(settings, stop)),
        ]
        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await close_redis()
            await dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "SpaceHawk Orbital Engine — internal domain/compute API "
            "(ingestion, catalog, propagation, screening, analytics). "
            "Reached only by the web/BFF tier over a private network; never serves HTML."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(conjunctions.router)
    app.include_router(debris.router)
    app.include_router(maneuvers.router)
    app.include_router(reports.router)
    app.include_router(audit.router)

    log.info("app.startup", environment=settings.environment, version=settings.version)
    return app


app = create_app()
