"""Celery tasks: periodic ingestion entry points.

Tasks are thin synchronous wrappers that drive the async ingestion runner via
``asyncio.run`` — the runner holds all the logic and is unit-tested directly.
"""

from __future__ import annotations

import asyncio

from orbital_engine.ingestion.cdm import ingest_cdms as _ingest_cdms
from orbital_engine.ingestion.runner import ingest_available, ingest_one
from orbital_engine.scheduler.celery_app import celery_app


@celery_app.task(name="orbital_engine.scheduler.tasks.ingest_source")
def ingest_source(source: str) -> dict[str, int]:
    """Ingest one source by its DataSource value (no-op if unavailable)."""
    return asyncio.run(ingest_one(source))


@celery_app.task(name="orbital_engine.scheduler.tasks.ingest_all")
def ingest_all() -> dict[str, int]:
    """Ingest every source configured in this environment."""
    return asyncio.run(ingest_available())


@celery_app.task(name="orbital_engine.scheduler.tasks.ingest_cdms")
def ingest_cdms() -> dict[str, int]:
    """Ingest recent Space-Track CDMs as conjunctions (no-op if unavailable)."""
    return {"written": asyncio.run(_ingest_cdms())}
