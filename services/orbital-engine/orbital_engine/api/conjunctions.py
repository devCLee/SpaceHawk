"""Conjunction + alert-log endpoints consumed by the web BFF (Stage 4).

``GET /conjunctions`` returns the ranked conjunction list the dashboard's
collisions panel renders (the contract the Stage-3 BFF stub already expects).
``GET /alerts`` and ``POST /alerts/{id}/ack`` back the alert center's triage
(list + acknowledge/dismiss). The live alert *stream* stays in ``api/catalog``
(``/alerts/stream``); these are the durable, queryable views.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from orbital_engine.repository import query_alerts, query_conjunctions, set_alert_status

router = APIRouter(tags=["conjunctions"])


class ConjunctionResponse(BaseModel):
    """One screened/CDM conjunction — mirrors the web `Conjunction` contract."""

    id: str
    source: str
    cdm_id: str | None = None
    primary_object_id: str
    primary_norad_cat_id: int | None = None
    primary_name: str
    secondary_object_id: str
    secondary_norad_cat_id: int | None = None
    secondary_name: str
    tca: datetime
    miss_distance_km: float
    relative_speed_km_s: float | None = None
    probability: float | None = None
    severity: str
    screened_at: datetime | None = None


class AlertResponse(BaseModel):
    """One durable alert in the triage log."""

    id: str
    type: str
    severity: str | None = None
    object_id: str | None = None
    conjunction_id: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AckRequest(BaseModel):
    status: Literal["ACK", "DISMISSED"] = "ACK"
    acknowledged_by: str | None = None


@router.get("/conjunctions", response_model=list[ConjunctionResponse], summary="Ranked conjunctions")
async def get_conjunctions(
    severity: str | None = Query(default=None, description="Exact tier: LOW / MOD / HIGH"),
    min_probability: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[dict[str, Any]]:
    return await query_conjunctions(severity=severity, min_probability=min_probability, limit=limit)


@router.get("/alerts", response_model=list[AlertResponse], summary="Durable alert log")
async def get_alerts(
    status: str | None = Query(default=None, description="NEW / ACK / DISMISSED"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return await query_alerts(status=status, limit=limit)


@router.post("/alerts/{alert_id}/ack", response_model=AlertResponse, summary="Acknowledge/dismiss an alert")
async def acknowledge_alert(alert_id: str, body: AckRequest) -> dict[str, Any]:
    updated = await set_alert_status(
        alert_id, status=body.status, acknowledged_by=body.acknowledged_by
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return updated
