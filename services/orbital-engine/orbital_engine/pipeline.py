"""The thin slice wired together: ingest-on-empty + a propagation/alert loop.

One background task drives the whole data plane for the spike:
  catalog rows -> server SGP4 -> Redis latest-state -> region rule -> alert pub.
The SSE endpoint (api/catalog.py) is the only consumer of the alert channel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from orbital_engine.alerts import AnomalyMonitor, ConjunctionAlerter, RegionMonitor, RpoMonitor
from orbital_engine.config import Settings
from orbital_engine.domain.maneuver import Maneuver
from orbital_engine.fingerprint import build_baseline, score_deviation
from orbital_engine.ingestion.cdm import fetch_cdms
from orbital_engine.ingestion.celestrak import fetch_celestrak
from orbital_engine.ingestion.runner import ingest_redundant
from orbital_engine.logging import get_logger
from orbital_engine.maneuver import detect_maneuvers
from orbital_engine.propagation.sgp4_service import propagate_objects
from orbital_engine.repository import (
    append_history,
    count_objects,
    fetch_catalog,
    fetch_catalog_elements,
    fetch_history,
    query_maneuvers,
    record_alert,
    upsert_baseline,
    upsert_conjunctions,
    upsert_maneuvers,
    upsert_objects,
)
from orbital_engine.rpo import screen_rpo
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


async def run_ingest_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Re-ingest the catalog on a cadence so gp_history accrues new epochs.

    Maneuver detection (run_maneuver_loop) needs a multi-epoch element-set series
    per object, and that series only grows when fresh TLEs at new epochs are
    appended to gp_history — which happens on ingest, not on propagation (the
    propagation loop reuses the standing mean elements, so it never produces a new
    epoch). ``ingest_if_empty`` seeds a single epoch at boot; without this loop the
    history stays one row deep and PREFIL skips every object (no maneuver ever
    detected). Runs slowly: TLEs refresh a few times a day and the feeds throttle.

    Uses ``ingest_redundant`` (Celestrak only), NOT ``ingest_available``: at this
    cadence (sub-hourly) re-querying Space-Track every tick would breach its
    ``class/gp`` 1/hour limit. Space-Track GP is owned solely by the hourly
    ``ingest-spacetrack`` Celery beat; both paths append to gp_history.
    """
    log.info("ingest.loop.start", interval=settings.catalog_ingest_interval_sec)
    while not stop.is_set():
        try:
            summary = await ingest_redundant(settings)
            log.info("ingest.cycle", **summary)
        except Exception as exc:  # noqa: BLE001 - one bad ingest must not kill the loop
            log.warning("ingest.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.catalog_ingest_interval_sec)
        except TimeoutError:
            pass
    log.info("ingest.loop.stop")


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
    # CDMs are pulled on their own (slow) cadence, NOT every screen cycle:
    # Space-Track suspends accounts that re-query public CDMs more than a few
    # times/day. The self-screen below still runs every cycle (it hits no
    # external API); only the official-CDM fetch is throttled to cdm_ingest_interval.
    last_cdm_fetch: datetime | None = None
    while not stop.is_set():
        try:
            now = datetime.now(UTC)
            if (
                last_cdm_fetch is None
                or (now - last_cdm_fetch).total_seconds() >= settings.cdm_ingest_interval_sec
            ):
                cdm_conjunctions = await fetch_cdms(settings)
                last_cdm_fetch = now
            else:
                cdm_conjunctions = []
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


async def run_rpo_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Screen the catalog for co-planar approachers of protected assets; alert.

    Stage 6 / roadmap P2a feature #12. Each cycle splits the catalog into the
    protected watch-list (``protected_norad_ids``) and everything else, runs the
    co-planar/co-altitude geometry screen, and records + publishes RPO alerts for
    new/escalated events into the Stage-4 alert center. A no-op while the
    watch-list is empty (the air-gap default until protected assets are loaded).
    """
    if not settings.protected_norad_ids:
        log.info("rpo.loop.skip", reason="no protected assets configured")
        return
    monitor = RpoMonitor(settings)
    protected_ids = {int(n) for n in settings.protected_norad_ids}
    log.info("rpo.loop.start", interval=settings.rpo_screen_interval_sec, protected=len(protected_ids))
    while not stop.is_set():
        try:
            rows = await fetch_catalog_elements(settings.ingest_limit)
            protected = [r for r in rows if r.get("norad_cat_id") in protected_ids]
            others = [r for r in rows if r.get("norad_cat_id") not in protected_ids]
            events = screen_rpo(protected, others, settings)
            for alert in monitor.evaluate(events):
                await record_alert(alert)
                await publish_alert(alert)
                log.info("rpo.alert", id=alert["id"], severity=alert["severity"])
            log.info("rpo.cycle", protected=len(protected), events=len(events))
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the loop
            log.warning("rpo.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.rpo_screen_interval_sec)
        except TimeoutError:
            pass
    log.info("rpo.loop.stop")


async def run_fingerprint_loop(settings: Settings, stop: asyncio.Event) -> None:
    """Rebuild per-object behavioral baselines; flag deviating maneuvers as alerts.

    Stage 6 / roadmap P2a feature #14 (the innovation spine). Each cycle, per
    catalogued object with enough maneuver history: build + persist its baseline
    (cadence + Δv fingerprint), then test its most-recent maneuver against the
    baseline of the *prior* maneuvers — so a new burn is judged against history,
    not against itself — and emit a maneuver-anomaly alert when it deviates.
    """
    monitor = AnomalyMonitor(settings)
    log.info("fingerprint.loop.start", interval=settings.fingerprint_interval_sec)
    while not stop.is_set():
        try:
            objects = await fetch_catalog(settings.ingest_limit)
            baselines, anomalies = 0, []
            for obj in objects:
                rows = await query_maneuvers(
                    object_id=obj["object_id"], limit=settings.maneuver_history_lookback
                )
                maneuvers = [Maneuver(**r) for r in rows]  # newest-first
                baseline = build_baseline(maneuvers, settings)
                if baseline is None:
                    continue
                await upsert_baseline(baseline)
                baselines += 1
                prior_baseline = build_baseline(maneuvers[1:], settings)
                if prior_baseline is not None:
                    dev = score_deviation(prior_baseline, maneuvers[0], settings)
                    anomalies.append((dev, maneuvers[0]))
            for alert in monitor.evaluate(anomalies):
                await record_alert(alert)
                await publish_alert(alert)
                log.info("fingerprint.anomaly", id=alert["id"], severity=alert["severity"])
            log.info("fingerprint.cycle", baselines=baselines)
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the loop
            log.warning("fingerprint.loop.error", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.fingerprint_interval_sec)
        except TimeoutError:
            pass
    log.info("fingerprint.loop.stop")
