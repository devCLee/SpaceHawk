"""DISCOS (ESA Database and Information System Characterising Objects in Space).

DISCOSweb supplies **physical characteristics** — object class, mass, shape,
dimensions, and radar cross-section — but **no orbital state** (no epoch, no mean
elements). It therefore cannot produce a standalone canonical ``SpaceObject``
(the model/DB require Keplerian elements). DISCOS is wired as a *metadata
enrichment* source instead: it is fetched on its own slow cadence and applied as
a targeted UPDATE onto catalog rows the element sources already created, matched
on NORAD (``satno``) or, failing that, COSPAR (``cosparId``). It is deliberately
*not* a ``SourceAdapter`` (those create rows); see repository.apply_enrichments.

The DISCOSweb REST API is JSON:API: ``GET /api/objects`` returns
``{data: [{id, type, attributes}], links: {next}, meta: {pagination}}``, is
Bearer-token authenticated, and is rate-limited (HTTP 429 + ``Retry-After``).
``normalize`` is pure (no network) so it is unit-tested from fixtures; the
``DiscosClient`` adds auth + pagination + the shared rate-limit/retry helpers.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from orbital_engine.config import Settings, get_settings
from orbital_engine.ingestion.http_util import RateLimiter, request_with_retry
from orbital_engine.logging import get_logger

log = get_logger("ingestion.discos")

OBJECTS_PATH = "/api/objects"
# DISCOS dimension keys, largest-of which becomes the representative span.
_DIMENSION_KEYS = ("span", "diameter", "length", "width", "height", "depth")


class DiscosEnrichment(BaseModel):
    """Physical characteristics for one object, keyed by NORAD/COSPAR identity.

    Not a catalog record — only an enrichment patch applied to an existing row.
    At least one of ``norad_cat_id`` / ``intl_designator`` must be present (the
    join key); records with neither are dropped in ``normalize``.
    """

    norad_cat_id: int | None = None
    intl_designator: str | None = None
    object_class: str | None = None
    mass_kg: float | None = None
    shape: str | None = None
    span_m: float | None = None
    cross_section_min_m2: float | None = None
    cross_section_avg_m2: float | None = None
    cross_section_max_m2: float | None = None


def _num(value: Any) -> float | None:
    """Coerce a DISCOS numeric attribute to float; treat missing/blank as None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _span(attrs: dict[str, Any]) -> float | None:
    """Largest linear dimension across the DISCOS size keys (metres)."""
    dims = [d for d in (_num(attrs.get(k)) for k in _DIMENSION_KEYS) if d is not None]
    return max(dims) if dims else None


def normalize(data: list[dict[str, Any]]) -> list[DiscosEnrichment]:
    """Map JSON:API ``data`` items to enrichment patches. Identity-less rows skipped."""
    out: list[DiscosEnrichment] = []
    for item in data:
        attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
        satno = attrs.get("satno")
        cospar = attrs.get("cosparId")
        norad = int(satno) if satno not in (None, "") else None
        if norad is None and not cospar:
            continue  # no join key -> can't attach to a catalog row
        out.append(
            DiscosEnrichment(
                norad_cat_id=norad,
                intl_designator=cospar or None,
                object_class=attrs.get("objectClass") or None,
                mass_kg=_num(attrs.get("mass")),
                shape=attrs.get("shape") or None,
                span_m=_span(attrs),
                cross_section_min_m2=_num(attrs.get("xSectMin")),
                cross_section_avg_m2=_num(attrs.get("xSectAvg")),
                cross_section_max_m2=_num(attrs.get("xSectMax")),
            )
        )
    return out


class DiscosClient:
    """Authenticated, rate-limited, paginating DISCOSweb REST client."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.discos_base_url,
            headers={"Authorization": f"Bearer {settings.discos_api_token}"},
            timeout=60.0,
            follow_redirects=True,
        )
        self._limiter = limiter or RateLimiter(settings.discos_max_requests_per_min)

    async def fetch_objects(self) -> list[dict[str, Any]]:
        """Page through ``/api/objects`` and return the concatenated JSON:API data.

        Follows ``meta.pagination`` page-by-page until the last page, a missing
        ``links.next``, or the configured object cap (``discos_query_limit``).
        """
        page_size = self.settings.discos_page_size
        limit = self.settings.discos_query_limit
        params: dict[str, Any] = {
            "page[size]": page_size,
            "page[number]": 1,
            "sort": "id",
        }
        collected: list[dict[str, Any]] = []
        while True:
            await self._limiter.acquire()
            resp = await request_with_retry(
                lambda p=dict(params): self._client.get(OBJECTS_PATH, params=p)
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", [])
            collected.extend(data)
            if limit is not None and len(collected) >= limit:
                collected = collected[:limit]
                break
            pagination = body.get("meta", {}).get("pagination", {})
            current = int(pagination.get("currentPage", params["page[number]"]))
            total = int(pagination.get("totalPages", current))
            if current >= total or not body.get("links", {}).get("next"):
                break
            params["page[number]"] = current + 1
        return collected

    async def aclose(self) -> None:
        await self._client.aclose()


async def fetch_discos(settings: Settings | None = None) -> list[DiscosEnrichment]:
    """Fetch the DISCOS catalog and normalize it to enrichment patches."""
    settings = settings or get_settings()
    client = DiscosClient(settings)
    try:
        data = await client.fetch_objects()
    finally:
        await client.aclose()
    enrichments = normalize(data)
    log.info("ingest.discos", fetched=len(data), kept=len(enrichments))
    return enrichments
