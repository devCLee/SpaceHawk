"""The thin slice wired together: ingest-on-empty + a propagation/alert loop.

One background task drives the whole data plane for the spike:
  catalog rows -> server SGP4 -> Redis latest-state -> region rule -> alert pub.
The SSE endpoint (api/catalog.py) is the only consumer of the alert channel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from orbital_engine.alerts import RegionMonitor
from orbital_engine.config import Settings
from orbital_engine.ingestion.celestrak import fetch_celestrak
from orbital_engine.logging import get_logger
from orbital_engine.propagation.sgp4_service import propagate_objects
from orbital_engine.repository import (
    append_history,
    count_objects,
    fetch_catalog,
    upsert_objects,
)
from orbital_engine.state import publish_alert, write_latest_state

log = get_logger("pipeline")


async def ingest_if_empty(settings: Settings) -> int:
    """Populate the catalog from Celestrak on first boot (idempotent-ish)."""
    if await count_objects() > 0:
        return 0
    objects = await fetch_celestrak(settings)
    written = await upsert_objects(objects)
    await append_history(objects)
    log.info("pipeline.ingest", written=written)
    return written


async def run_propagation_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Propagate the set every tick; refresh Redis; publish region-entry alerts."""
    monitor = RegionMonitor(settings)
    log.info("pipeline.loop.start", interval=settings.propagation_interval_sec)
    while not stop.is_set():
        try:
            rows = await fetch_catalog(settings.ingest_limit)
            states = propagate_objects(rows)
            await write_latest_state(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "count": len(states),
                    "objects": states,
                }
            )
            for alert in monitor.evaluate(states):
                await publish_alert(alert)
                log.info("pipeline.alert", object_id=alert["object_id"])
        except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the loop
            log.warning("pipeline.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.propagation_interval_sec)
        except TimeoutError:
            pass
    log.info("pipeline.loop.stop")
