"""Catalog / state / alert endpoints consumed by the web BFF.

Typed response models keep the contract in the OpenAPI document so the generated
TS client stays in sync. The alert stream is Server-Sent Events (dev-plan §4.5:
one-way push, proxy-friendly, auto-reconnect).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orbital_engine.config import get_settings
from orbital_engine.ingestion.celestrak import fetch_celestrak
from orbital_engine.repository import fetch_catalog, upsert_objects
from orbital_engine.state import ALERT_CHANNEL, get_client, read_latest_state

router = APIRouter(tags=["catalog"])


class CatalogObject(BaseModel):
    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    object_type: str | None = None
    country_code: str | None = None
    tle_line0: str | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None


class IngestResult(BaseModel):
    written: int


class StateObject(BaseModel):
    object_id: str | None = None
    object_name: str | None = None
    lat_deg: float
    lon_deg: float
    alt_km: float


class LatestState(BaseModel):
    generated_at: str | None = None
    count: int = 0
    objects: list[StateObject] = Field(default_factory=list)


@router.get("/catalog", response_model=list[CatalogObject], summary="Current catalog")
async def get_catalog() -> list[dict[str, Any]]:
    settings = get_settings()
    rows = await fetch_catalog(settings.ingest_limit)
    return rows


@router.post("/ingest/run", response_model=IngestResult, summary="Trigger Celestrak ingest")
async def run_ingest() -> IngestResult:
    objects = await fetch_celestrak(get_settings())
    written = await upsert_objects(objects)
    return IngestResult(written=written)


@router.get("/state/latest", response_model=LatestState, summary="Latest propagated state")
async def get_latest_state() -> LatestState:
    state = await read_latest_state()
    return LatestState.model_validate(state) if state else LatestState()


@router.get("/alerts/stream", summary="Alert stream (SSE)")
async def alerts_stream() -> StreamingResponse:
    async def event_source() -> AsyncIterator[bytes]:
        pubsub = get_client().pubsub()
        await pubsub.subscribe(ALERT_CHANNEL)
        try:
            # Prime the connection so proxies/EventSource open immediately.
            yield b": connected\n\n"
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    yield b": keep-alive\n\n"  # heartbeat
                    continue
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                yield f"event: alert\ndata: {data}\n\n".encode()
        finally:
            await pubsub.unsubscribe(ALERT_CHANNEL)
            await pubsub.aclose()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
