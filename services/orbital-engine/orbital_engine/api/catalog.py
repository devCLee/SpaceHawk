"""Catalog / state / alert endpoints consumed by the web BFF.

Typed response models keep the contract in the OpenAPI document so the generated
TS client stays in sync. The alert stream is Server-Sent Events (dev-plan §4.5:
one-way push, proxy-friendly, auto-reconnect).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orbital_engine.config import get_settings
from orbital_engine.ingestion.celestrak import fetch_celestrak
from orbital_engine.repository import (
    append_history,
    fetch_history,
    get_object,
    query_catalog,
    upsert_objects,
)
from orbital_engine.state import ALERT_CHANNEL, get_client, read_latest_state, read_object_state

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


class ObjectDetail(BaseModel):
    """Full catalog record for the per-satellite info sidebar (#9h)."""

    object_id: str
    norad_cat_id: int | None = None
    intl_designator: str | None = None
    data_source: str | None = None
    originator: str | None = None
    object_name: str
    object_type: str | None = None
    rcs_size: str | None = None
    classification_type: str | None = None
    country_code: str | None = None
    launch_date: date | None = None
    decay_date: date | None = None
    site: str | None = None
    epoch: datetime | None = None
    mean_motion: float | None = None
    eccentricity: float | None = None
    inclination: float | None = None
    ra_of_asc_node: float | None = None
    arg_of_pericenter: float | None = None
    mean_anomaly: float | None = None
    ephemeris_type: int | None = None
    bstar: float | None = None
    mean_motion_dot: float | None = None
    mean_motion_ddot: float | None = None
    semimajor_axis_km: float | None = None
    period_min: float | None = None
    apoapsis_km: float | None = None
    periapsis_km: float | None = None
    mean_element_theory: str | None = None
    ref_frame: str | None = None
    tle_line0: str | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None
    ingested_at: datetime | None = None


class HistoryPoint(BaseModel):
    """One element set in an object's time series (gp_history)."""

    object_id: str
    epoch: datetime
    data_source: str | None = None
    mean_motion: float | None = None
    eccentricity: float | None = None
    inclination: float | None = None
    ra_of_asc_node: float | None = None
    arg_of_pericenter: float | None = None
    mean_anomaly: float | None = None
    bstar: float | None = None
    semimajor_axis_km: float | None = None
    period_min: float | None = None
    apoapsis_km: float | None = None
    periapsis_km: float | None = None


@router.get("/catalog", response_model=list[CatalogObject], summary="Query the catalog")
async def get_catalog(
    q: str | None = Query(default=None, description="Name / intl-designator / NORAD substring"),
    object_type: str | None = Query(default=None, description="PAYLOAD / ROCKET BODY / DEBRIS / ..."),
    country_code: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return await query_catalog(
        q=q,
        object_type=object_type,
        country_code=country_code,
        limit=limit,
        offset=offset,
    )


@router.get("/catalog/{object_id}", response_model=ObjectDetail, summary="Object detail")
async def get_object_detail(object_id: str) -> dict[str, Any]:
    row = await get_object(object_id)
    if row is None:
        raise HTTPException(status_code=404, detail="object not found")
    return row


@router.get(
    "/catalog/{object_id}/history",
    response_model=list[HistoryPoint],
    summary="Object element-set history",
)
async def get_object_history(
    object_id: str,
    limit: int = Query(default=500, ge=1, le=10000),
) -> list[dict[str, Any]]:
    return await fetch_history(object_id, limit=limit)


@router.get("/catalog/{object_id}/state", response_model=StateObject, summary="Object latest state")
async def get_object_latest_state(object_id: str) -> dict[str, Any]:
    state = await read_object_state(object_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no current state for object")
    return state


@router.post("/ingest/run", response_model=IngestResult, summary="Trigger Celestrak ingest")
async def run_ingest() -> IngestResult:
    objects = await fetch_celestrak(get_settings())
    written = await upsert_objects(objects)
    await append_history(objects)
    return IngestResult(written=written)


@router.get("/state/latest", response_model=LatestState, summary="Latest propagated state")
async def get_latest_state() -> LatestState:
    state = await read_latest_state()
    return LatestState.model_validate(state) if state else LatestState()


@router.get("/state/stream", summary="Live latest-state stream (SSE)")
async def state_stream() -> StreamingResponse:
    """Push the latest propagated snapshot on each propagation cycle (one-way SSE).

    Lets the dashboard receive live-state deltas without polling; the browser
    interpolates between snapshots (dev-plan §4.2/§4.5).
    """
    interval = float(get_settings().propagation_interval_sec)

    async def event_source() -> AsyncIterator[bytes]:
        yield b": connected\n\n"
        last_generated: str | None = None
        while True:
            state = await read_latest_state()
            if state is not None and state.get("generated_at") != last_generated:
                last_generated = state.get("generated_at")
                yield f"event: state\ndata: {json.dumps(state)}\n\n".encode()
            else:
                yield b": keep-alive\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


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
