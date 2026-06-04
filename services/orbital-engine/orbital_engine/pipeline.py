"""The thin slice wired together: ingest-on-empty + a propagation/alert loop.

One background task drives the whole data plane for the spike:
  catalog rows -> server SGP4 -> Redis latest-state -> region rule -> alert pub.
The SSE endpoint (api/catalog.py) is the only consumer of the alert channel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from orbital_engine.alerts import ConjunctionAlerter, RegionMonitor
from orbital_engine.config import Settings
from orbital_engine.ingestion.cdm import fetch_cdms
from orbital_engine.ingestion.celestrak import fetch_celestrak
from orbital_engine.logging import get_logger
from orbital_engine.maneuver import detect_maneuvers
from orbital_engine.propagation.sgp4_service import propagate_objects
from orbital_engine.repository import (
    append_history,
    count_objects,
    fetch_catalog,
    fetch_history,
    record_alert,
    upsert_conjunctions,
    upsert_maneuvers,
    upsert_objects,
)
from orbital_engine.screening import screen_objects
from orbital_engine.state import publish_alert, write_latest_state, write_object_states

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
            await write_object_states(states, settings.state_ttl_sec)
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


async def run_screening_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Screen for conjunctions every cycle; persist them and fan out alerts.

    Each cycle ingests any official CDMs (no-op without Space-Track creds), self-
    screens the catalog (dev-plan §5 Stage 4), upserts both into the conjunction
    store, then records + publishes alerts for new/escalated events at or above
    the trust-calibrated tier floor. Runs far less often than the propagation
    loop — screening is heavier and conjunctions evolve slowly.
    """
    alerter = ConjunctionAlerter(settings)
    log.info("screening.loop.start", interval=settings.conjunction_screen_interval_sec)
    while not stop.is_set():
        try:
            cdm_conjunctions = await fetch_cdms(settings)
            rows = await fetch_catalog(settings.ingest_limit)
            screened = screen_objects(rows, settings)
            written = await upsert_conjunctions(cdm_conjunctions + screened)
            for alert in alerter.evaluate(cdm_conjunctions + screened):
                await record_alert(alert)
                await publish_alert(alert)
                log.info("screening.alert", id=alert["id"], severity=alert["severity"])
            log.info("screening.cycle", screened=len(screened), cdms=len(cdm_conjunctions), written=written)
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the loop
            log.warning("screening.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.conjunction_screen_interval_sec)
        except TimeoutError:
            pass
    log.info("screening.loop.stop")


async def run_maneuver_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Scan each object's element history for maneuvers; persist detections.

    Stage 6 / roadmap P2a feature #10. Runs on its own (slow) cadence: maneuvers
    are detected over the multi-epoch ``gp_history`` series, which only grows as
    new element sets ingest, so re-scanning faster than ingest buys nothing. The
    V-pattern detector (``orbital_engine.maneuver``) is pure; this loop is just
    the per-object fan-out over the catalog (bounded by ``ingest_limit``).
    """
    log.info("maneuver.loop.start", interval=settings.maneuver_detect_interval_sec)
    while not stop.is_set():
        try:
            rows = await fetch_catalog(settings.ingest_limit)
            detected = 0
            for row in rows:
                history = await fetch_history(
                    row["object_id"], limit=settings.maneuver_history_lookback
                )
                # fetch_history is identity-light; carry the catalog name/norad so
                # detections are labelled without a second query per object.
                identity = {"object_name": row.get("object_name"), "norad_cat_id": row.get("norad_cat_id")}
                maneuvers = detect_maneuvers([{**h, **identity} for h in history], settings)
                detected += await upsert_maneuvers(maneuvers)
            log.info("maneuver.cycle", objects=len(rows), detected=detected)
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the loop
            log.warning("maneuver.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.maneuver_detect_interval_sec)
        except TimeoutError:
            pass
    log.info("maneuver.loop.stop")
