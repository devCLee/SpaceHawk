"""Ingestion runner: fetch sources -> merge -> persist.

The reusable core a scheduler tick (or an on-demand trigger) drives. Sources
are fetched concurrently; a failure in one source is logged and skipped so a
single bad feed never blocks the rest (multi-source redundancy is a roadmap
risk control). The combined records are de-duplicated/merged into one canonical
record each, upserted, and appended to the element-set history.
"""

from __future__ import annotations

import asyncio

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, SpaceObject
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.ingestion.discos import fetch_discos
from orbital_engine.ingestion.merge import merge_objects
from orbital_engine.ingestion.registry import available_adapters
from orbital_engine.logging import get_logger
from orbital_engine.repository import append_history, apply_enrichments, upsert_objects

log = get_logger("ingestion.runner")


async def ingest_sources(adapters: list[SourceAdapter]) -> dict[str, int]:
    """Fetch the given sources, merge, and persist. Returns a small summary."""
    if not adapters:
        return {"sources": 0, "fetched": 0, "written": 0}
    results = await asyncio.gather(*(a.fetch() for a in adapters), return_exceptions=True)
    objects: list[SpaceObject] = []
    for adapter, result in zip(adapters, results, strict=True):
        if isinstance(result, Exception):
            log.warning("ingest.source.error", source=adapter.source.value, error=str(result))
            continue
        objects.extend(result)
    merged = merge_objects(objects)
    written = await upsert_objects(merged)
    await append_history(merged)
    log.info("ingest.run", sources=len(adapters), fetched=len(objects), written=written)
    return {"sources": len(adapters), "fetched": len(objects), "written": written}


async def ingest_available(settings: Settings | None = None) -> dict[str, int]:
    """Run every source configured in this environment."""
    return await ingest_sources(available_adapters(settings))


async def ingest_redundant(settings: Settings | None = None) -> dict[str, int]:
    """Run only the redundant/low-latency sources — everything except Space-Track.

    Space-Track's API caps ``class/gp`` polling at 1/hour, so it must have a
    single owner: the hourly Celery beat (``ingest-spacetrack``). The in-process
    accrual loop (``pipeline.run_ingest_loop``) runs far more often to keep
    ``gp_history`` fresh, so it calls this — fetching only Celestrak — instead of
    ``ingest_available``, which would re-query Space-Track every loop tick and
    breach the 1/hour limit.
    """
    settings = settings or get_settings()
    adapters = [
        a for a in available_adapters(settings) if a.source is not DataSource.SPACE_TRACK
    ]
    return await ingest_sources(adapters)


async def ingest_one(source: str, settings: Settings | None = None) -> dict[str, int]:
    """Run a single source by its DataSource value (skips if unavailable)."""
    settings = settings or get_settings()
    adapters = [a for a in available_adapters(settings) if a.source.value == source]
    return await ingest_sources(adapters)


async def enrich_discos(settings: Settings | None = None) -> dict[str, int]:
    """Fetch DISCOS physical characteristics and patch them onto catalog rows.

    Distinct from ``ingest_*``: DISCOS carries no orbital state, so it creates no
    rows — it only enriches existing ones (matched on NORAD/COSPAR). A no-op
    (``available`` 0) without a DISCOS token, so the static schedule is safe.
    """
    settings = settings or get_settings()
    if not settings.discos_api_token:
        log.info("enrich.discos.skip", reason="no DISCOS token")
        return {"available": 0, "fetched": 0, "applied": 0}
    enrichments = await fetch_discos(settings)
    rows = [e.model_dump(mode="python") for e in enrichments]
    applied = await apply_enrichments(rows)
    log.info("enrich.discos", fetched=len(rows), applied=applied)
    return {"available": 1, "fetched": len(rows), "applied": applied}
