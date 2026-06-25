"""CCSDS Conjunction Data Message (CDM) ingestion from Space-Track.

Space-Track's public ``cdm_public`` class publishes screened conjunctions for the
on-orbit catalog. Each record maps onto the canonical :class:`Conjunction`; the
severity tier is derived the same way as engine-screened events so CDM-sourced
and self-screened conjunctions are interchangeable downstream.

``normalize_cdm`` is pure (no network) so contract tests run from fixtures. Live
fetch is gated on Space-Track credentials and, in the enclave, points at the
cross-domain mirror (air-gap §4.6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.conjunction import (
    Conjunction,
    ConjunctionSource,
    TierThresholds,
    make_conjunction_id,
    severity_for,
    usoid_for_norad,
)
from orbital_engine.logging import get_logger
from orbital_engine.state import read_sync_marker, write_sync_marker

log = get_logger("ingestion.cdm")

# Sync-marker scope distinct from the GP watermark so CDM and GP advance apart.
CDM_MARKER_SCOPE = "SPACE-TRACK:CDM"


def _num(value: Any) -> float | None:
    """Parse a possibly-blank Space-Track numeric field; None when missing."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


def normalize_cdm(
    records: list[dict[str, Any]],
    *,
    thresholds: TierThresholds | None = None,
    limit: int | None = None,
) -> list[Conjunction]:
    """Map Space-Track ``cdm_public`` JSON onto canonical conjunctions.

    Rows missing the fields required to be actionable (a TCA and a miss distance)
    are skipped rather than failing the batch.
    """
    thresholds = thresholds or TierThresholds()
    out: list[Conjunction] = []
    for rec in records:
        tca_raw = rec.get("TCA")
        miss = _num(rec.get("MIN_RNG"))
        if not tca_raw or miss is None:
            log.warning("cdm.skip", cdm_id=rec.get("CDM_ID"))
            continue
        try:
            tca = datetime.fromisoformat(tca_raw)
        except ValueError:
            log.warning("cdm.skip.tca", cdm_id=rec.get("CDM_ID"), tca=tca_raw)
            continue

        cdm_id = str(rec["CDM_ID"]) if rec.get("CDM_ID") is not None else None
        p_norad = _int(rec.get("SAT_1_ID"))
        s_norad = _int(rec.get("SAT_2_ID"))
        p_name = rec.get("SAT_1_NAME") or (str(p_norad) if p_norad else "UNKNOWN")
        s_name = rec.get("SAT_2_NAME") or (str(s_norad) if s_norad else "UNKNOWN")
        primary_id = usoid_for_norad(p_norad, fallback=f"SH:SRC:CDM:{cdm_id}:1")
        secondary_id = usoid_for_norad(s_norad, fallback=f"SH:SRC:CDM:{cdm_id}:2")
        probability = _num(rec.get("PC"))

        out.append(
            Conjunction(
                id=make_conjunction_id(
                    source=ConjunctionSource.CDM,
                    cdm_id=cdm_id,
                    primary_object_id=primary_id,
                    secondary_object_id=secondary_id,
                    tca=tca,
                ),
                source=ConjunctionSource.CDM,
                cdm_id=cdm_id,
                primary_object_id=primary_id,
                primary_norad_cat_id=p_norad,
                primary_name=p_name,
                secondary_object_id=secondary_id,
                secondary_norad_cat_id=s_norad,
                secondary_name=s_name,
                tca=tca,
                miss_distance_km=miss,
                probability=probability,
                severity=severity_for(probability, miss, thresholds),
            )
        )
        if limit is not None and len(out) >= limit:
            break
    return out


async def fetch_cdms(settings: Settings | None = None) -> list[Conjunction]:
    """Fetch + normalize recent CDMs from Space-Track (incremental, watermarked).

    Returns an empty list when Space-Track is not configured (air-gap/dev), so the
    caller can run unconditionally.
    """
    # Imported here to avoid a module import cycle (spacetrack imports config).
    from orbital_engine.ingestion.spacetrack import SpaceTrackClient

    settings = settings or get_settings()
    if not (settings.spacetrack_identity and settings.spacetrack_password):
        return []

    since_iso = await read_sync_marker(CDM_MARKER_SCOPE)
    watermark = datetime.fromisoformat(since_iso) if since_iso else None
    # Clamp the lower bound up to a recent horizon so a stale/ancient watermark
    # cannot trap ingestion in weeks-old CDMs (Space-Track's "/CREATED/>now-1/"
    # recent-window pattern). Naive UTC to match the watermark's stored format
    # (_fmt writes naive UTC strings). When the watermark is fresh it wins, so a
    # healthy feed stays incremental; when it is stale the horizon wins and the
    # next fetch self-heals to the present.
    horizon = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=settings.cdm_lookback_days)
    since = max(watermark, horizon) if watermark is not None else horizon
    client = SpaceTrackClient(settings)
    try:
        records = await client.query_cdm(since, limit=settings.cdm_query_limit)
    finally:
        await client.aclose()

    conjunctions = normalize_cdm(records, thresholds=settings.tier_thresholds())
    newest = _newest_creation_date(records)
    if newest:
        await write_sync_marker(CDM_MARKER_SCOPE, newest)
    log.info("ingest.cdm", since=since.isoformat(), fetched=len(records), kept=len(conjunctions))
    return conjunctions


def _newest_creation_date(records: list[dict[str, Any]]) -> str | None:
    """Max CREATED in a batch (Space-Track's uniform datetime format sorts lexically)."""
    dates = [rec["CREATED"] for rec in records if rec.get("CREATED")]
    return max(dates) if dates else None


async def ingest_cdms(settings: Settings | None = None) -> int:
    """Fetch CDMs and upsert them as conjunctions. Returns the number written."""
    # Imported here to keep ingestion modules importable without the DB layer.
    from orbital_engine.repository import upsert_conjunctions

    conjunctions = await fetch_cdms(settings)
    return await upsert_conjunctions(conjunctions)
