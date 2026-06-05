"""Celestrak GP ingestion (the thin slice's one source).

Celestrak's GP JSON carries the OMM mean elements + most metadata but *not* the
raw TLE lines; its TLE export carries the lines but little metadata. We fetch
both for one group and merge them by NORAD id, so each canonical record holds
the TLE lines the propagator (server) and satellite.js (client) both consume.

``normalize`` is pure (no network) so tests can drive it from fixtures.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, ObjectType, SpaceObject
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.logging import get_logger

log = get_logger("ingestion.celestrak")


def _parse_tle_text(text: str) -> dict[int, tuple[str, str, str]]:
    """Parse 3-line TLE export -> {norad_id: (line0, line1, line2)}."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out: dict[int, tuple[str, str, str]] = {}
    for i in range(0, len(lines) - 2, 3):
        l0, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if not (l1.startswith("1 ") and l2.startswith("2 ")):
            continue
        try:
            norad = int(l1[2:7])
        except ValueError:
            continue
        out[norad] = (l0, l1, l2)
    return out


def normalize(
    omm_records: list[dict[str, Any]],
    tle_text: str,
    *,
    limit: int | None = None,
) -> list[SpaceObject]:
    """Merge OMM JSON + TLE export into canonical records (TLE-bearing only)."""
    tle_by_norad = _parse_tle_text(tle_text)
    objects: list[SpaceObject] = []
    for rec in omm_records:
        norad = rec.get("NORAD_CAT_ID")
        tle = tle_by_norad.get(int(norad)) if norad is not None else None
        if tle is None:
            # Without TLE lines we can't propagate in the slice; skip.
            continue
        l0, l1, l2 = tle
        payload = dict(rec)
        payload.setdefault("OBJECT_TYPE", ObjectType.UNKNOWN.value)
        payload["data_source"] = DataSource.CELESTRAK.value
        payload["TLE_LINE0"] = l0
        payload["TLE_LINE1"] = l1
        payload["TLE_LINE2"] = l2
        try:
            objects.append(SpaceObject.model_validate(payload))
        except Exception as exc:  # noqa: BLE001 - skip a bad record, keep ingesting
            log.warning("normalize.skip", norad=norad, error=str(exc))
        if limit is not None and len(objects) >= limit:
            break
    return objects


def _is_throttled(resp: httpx.Response) -> bool:
    """True if Celestrak refused a repeat same-group download (its rate-limit 403).

    Celestrak tracks the last successful download per GROUP and answers a repeat
    request with HTTP 403 + a body like "GP data has not updated since your last
    successful download of GROUP=...". Because one ingest fetches the group twice
    (OMM JSON then TLE export), the second request can trip this — and it means
    "no new data", not a hard failure.
    """
    return resp.status_code == 403 and "not updated" in resp.text.lower()


async def fetch_celestrak(settings: Settings | None = None) -> list[SpaceObject]:
    """Fetch one Celestrak GP group (JSON + TLE) and normalize it.

    Returns ``[]`` (non-fatal) when Celestrak rate-limits the group (see
    :func:`_is_throttled`): a 403 throttle is "nothing new this cycle", and must
    not raise into a 500 or abort the multi-source ingest. Space-Track is the
    authoritative populator; Celestrak is the redundant/low-latency source.
    """
    settings = settings or get_settings()
    params_json = {"GROUP": settings.celestrak_group, "FORMAT": "json"}
    params_tle = {"GROUP": settings.celestrak_group, "FORMAT": "tle"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        omm_resp = await client.get(settings.celestrak_gp_url, params=params_json)
        tle_resp = await client.get(settings.celestrak_gp_url, params=params_tle)
    for resp in (omm_resp, tle_resp):
        if _is_throttled(resp):
            log.info("ingest.celestrak.throttled", group=settings.celestrak_group)
            return []
        resp.raise_for_status()
    objects = normalize(omm_resp.json(), tle_resp.text, limit=settings.ingest_limit)
    log.info("ingest.celestrak", group=settings.celestrak_group, count=len(objects))
    return objects


class CelestrakAdapter(SourceAdapter):
    """Celestrak GP source behind the uniform adapter interface.

    Always available: Celestrak needs no credentials (in the enclave the URL is
    repointed at the offline mirror). Delegates to the module-level fetch/normalize
    so the existing pure-function tests keep covering the parsing logic.
    """

    source: ClassVar[DataSource] = DataSource.CELESTRAK

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch(self) -> list[SpaceObject]:
        return await fetch_celestrak(self.settings)
