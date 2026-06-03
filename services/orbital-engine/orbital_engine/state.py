"""Hot state + alert pub/sub (Redis).

Per the architecture (dev-plan §2.2), Redis holds the latest propagated state
(one snapshot for the whole tracked set) and carries the alert channel that the
SSE endpoint fans out to the browser. Keys are intentionally trivial for the
thin slice; Stage 2 introduces per-object keys and TTLs.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from orbital_engine.config import get_settings

LATEST_STATE_KEY = "state:latest"
ALERT_CHANNEL = "alerts"
SYNC_MARKER_PREFIX = "sync:marker:"  # + source name -> ISO timestamp of last sync

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def ping() -> bool:
    """True if Redis answers PING; never raises."""
    try:
        return bool(await get_client().ping())
    except Exception:  # noqa: BLE001 - readiness must not propagate
        return False


async def write_latest_state(state: dict[str, Any]) -> None:
    await get_client().set(LATEST_STATE_KEY, json.dumps(state))


async def read_latest_state() -> dict[str, Any] | None:
    raw = await get_client().get(LATEST_STATE_KEY)
    return json.loads(raw) if raw else None


async def publish_alert(alert: dict[str, Any]) -> None:
    await get_client().publish(ALERT_CHANNEL, json.dumps(alert))


async def read_sync_marker(source: str) -> str | None:
    """Last successful incremental-sync watermark (ISO ts) for a source, if any."""
    return await get_client().get(f"{SYNC_MARKER_PREFIX}{source}")


async def write_sync_marker(source: str, iso_timestamp: str) -> None:
    """Persist the incremental-sync watermark for a source."""
    await get_client().set(f"{SYNC_MARKER_PREFIX}{source}", iso_timestamp)


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
