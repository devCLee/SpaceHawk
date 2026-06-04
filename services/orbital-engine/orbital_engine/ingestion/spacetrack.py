"""Space-Track connector — the authoritative primary source (Stage 2).

Space-Track's ``gp`` class returns the OMM mean elements *and* the TLE lines in
one record, so (unlike Celestrak) no separate TLE merge is needed: each row maps
straight onto the canonical ``SpaceObject``.

Design for the dev plan's requirements:
  * **authenticated session** — cookie login, reused across queries;
  * **rate limits** — every request goes through a ``RateLimiter`` kept under
    Space-Track's 30 req/min ceiling;
  * **retry / backoff** — transient failures retried via ``request_with_retry``;
  * **incremental sync** — query ``gp`` by ``CREATION_DATE > <last-watermark>``
    and advance the watermark (Redis) after a successful pull.

Query builders and ``normalize_gp`` are pure (no network), so contract tests run
from recorded fixtures. Live use is gated by credentials (``available()``); in
the air-gapped enclave the base URL points at the cross-domain mirror.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, ClassVar

import httpx

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, ObjectType, SpaceObject
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.ingestion.http_util import RateLimiter, request_with_retry
from orbital_engine.logging import get_logger
from orbital_engine.state import read_sync_marker, write_sync_marker

log = get_logger("ingestion.spacetrack")

QUERY_PREFIX = "/basicspacedata/query"
LOGIN_PATH = "/ajaxauth/login"


def _fmt(dt: datetime) -> str:
    """Space-Track's predicate datetime format."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_gp_query(since: datetime | None = None, *, limit: int | None = None) -> str:
    """Predicate path for the ``gp`` class.

    Incremental when ``since`` is given (records created after the watermark);
    otherwise the full on-orbit set (``decay_date`` null). Ordered by
    ``CREATION_DATE`` so the watermark advances monotonically.
    """
    parts = ["class", "gp"]
    if since is not None:
        parts += ["CREATION_DATE", f">{_fmt(since)}"]
    else:
        parts += ["decay_date", "null-val"]
    parts += ["orderby", "CREATION_DATE asc", "format", "json"]
    if limit is not None:
        parts += ["limit", str(int(limit))]
    return f"{QUERY_PREFIX}/" + "/".join(parts)


def build_satcat_query(*, limit: int | None = None) -> str:
    """Predicate path for the ``satcat`` class (object metadata / launch data)."""
    parts = ["class", "satcat", "orderby", "NORAD_CAT_ID asc", "format", "json"]
    if limit is not None:
        parts += ["limit", str(int(limit))]
    return f"{QUERY_PREFIX}/" + "/".join(parts)


def build_cdm_query(since: datetime | None = None, *, limit: int | None = None) -> str:
    """Predicate path for the public ``cdm_public`` class (conjunction data messages).

    Full parsing/screening is Stage 4 (#7); this makes CDMs queryable now.
    """
    parts = ["class", "cdm_public"]
    if since is not None:
        parts += ["CREATION_DATE", f">{_fmt(since)}"]
    parts += ["orderby", "CREATION_DATE asc", "format", "json"]
    if limit is not None:
        parts += ["limit", str(int(limit))]
    return f"{QUERY_PREFIX}/" + "/".join(parts)


def build_tip_query(since: datetime | None = None, *, limit: int | None = None) -> str:
    """Predicate path for the ``tip`` class (tracking & impact prediction / re-entry)."""
    parts = ["class", "tip"]
    if since is not None:
        parts += ["MSG_EPOCH", f">{_fmt(since)}"]
    parts += ["orderby", "MSG_EPOCH asc", "format", "json"]
    if limit is not None:
        parts += ["limit", str(int(limit))]
    return f"{QUERY_PREFIX}/" + "/".join(parts)


def normalize_gp(records: list[dict[str, Any]], *, limit: int | None = None) -> list[SpaceObject]:
    """Map Space-Track ``gp`` JSON onto canonical records. Bad rows are skipped."""
    objects: list[SpaceObject] = []
    for rec in records:
        payload = dict(rec)
        payload["data_source"] = DataSource.SPACE_TRACK.value
        payload.setdefault("OBJECT_TYPE", ObjectType.UNKNOWN.value)
        try:
            objects.append(SpaceObject.model_validate(payload))
        except Exception as exc:  # noqa: BLE001 - skip a bad record, keep ingesting
            log.warning("normalize.skip", norad=rec.get("NORAD_CAT_ID"), error=str(exc))
            continue
        if limit is not None and len(objects) >= limit:
            break
    return objects


def _newest_creation_date(records: list[dict[str, Any]]) -> str | None:
    """The max CREATION_DATE in a batch (Space-Track's uniform format sorts lexically)."""
    dates = [rec["CREATION_DATE"] for rec in records if rec.get("CREATION_DATE")]
    return max(dates) if dates else None


class SpaceTrackClient:
    """Authenticated, rate-limited, retrying Space-Track REST client."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.spacetrack_base_url, timeout=60.0, follow_redirects=True
        )
        self._limiter = limiter or RateLimiter(settings.spacetrack_max_requests_per_min)
        self._authenticated = False

    async def login(self) -> None:
        await self._limiter.acquire()
        data = {
            "identity": self.settings.spacetrack_identity,
            "password": self.settings.spacetrack_password,
        }
        resp = await request_with_retry(lambda: self._client.post(LOGIN_PATH, data=data))
        resp.raise_for_status()
        self._authenticated = True
        log.info("spacetrack.login")

    async def query(self, predicate_path: str) -> list[dict[str, Any]]:
        if not self._authenticated:
            await self.login()
        await self._limiter.acquire()
        resp = await request_with_retry(lambda: self._client.get(predicate_path))
        resp.raise_for_status()
        return resp.json()

    async def query_gp(
        self, since: datetime | None = None, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        return await self.query(build_gp_query(since, limit=limit))

    async def query_cdm(
        self, since: datetime | None = None, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch public Conjunction Data Messages (incremental by CREATION_DATE)."""
        return await self.query(build_cdm_query(since, limit=limit))

    async def aclose(self) -> None:
        await self._client.aclose()


class SpaceTrackAdapter(SourceAdapter):
    """Space-Track GP behind the uniform interface, with incremental sync."""

    source: ClassVar[DataSource] = DataSource.SPACE_TRACK

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client_factory: Callable[[], SpaceTrackClient] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client_factory = client_factory or (lambda: SpaceTrackClient(self.settings))

    def available(self) -> bool:
        return bool(self.settings.spacetrack_identity and self.settings.spacetrack_password)

    async def fetch(self) -> list[SpaceObject]:
        since_iso = await read_sync_marker(self.source.value)
        since = datetime.fromisoformat(since_iso) if since_iso else None
        client = self._client_factory()
        try:
            records = await client.query_gp(since, limit=self.settings.spacetrack_query_limit)
        finally:
            await client.aclose()
        objects = normalize_gp(records, limit=self.settings.spacetrack_query_limit)
        newest = _newest_creation_date(records)
        if newest:
            await write_sync_marker(self.source.value, newest)
        log.info("ingest.spacetrack", since=since_iso, fetched=len(records), kept=len(objects))
        return objects
