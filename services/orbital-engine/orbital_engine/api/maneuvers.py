"""Maneuver-intelligence endpoints consumed by the web BFF (Stage 6).

``GET /maneuvers`` returns detected maneuvers (Δv / RIC + rule-based purpose +
the V-pattern evidence) the dashboard's explainability panel renders;
``GET /maneuvers/baselines`` returns the per-object behavioral fingerprints. Both
sit in the ``MANEUVER_INTEL`` data domain (P0-RBAC-ABAC §2) — the analyst-tier
intelligence surface, not the general catalog.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from orbital_engine.repository import query_baselines, query_maneuvers
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires

router = APIRouter(tags=["maneuvers"])


class ManeuverResponse(BaseModel):
    """One detected maneuver — mirrors the canonical ``Maneuver`` record."""

    id: str
    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    epoch_before: datetime
    epoch_after: datetime
    detected_epoch: datetime
    delta_sma_km: float
    delta_ecc: float
    delta_inc_deg: float
    delta_raan_deg: float
    detection_statistic: float
    confidence: float
    sma_before_km: float | None = None
    inclination_deg: float | None = None
    delta_v_m_s: float | None = None
    ric_radial_m_s: float | None = None
    ric_in_track_m_s: float | None = None
    ric_cross_track_m_s: float | None = None
    maneuver_type: str
    detected_at: datetime | None = None


class BaselineResponse(BaseModel):
    """One object's behavioral fingerprint — mirrors ``ManeuverBaseline``."""

    object_id: str
    object_name: str
    sample_count: int
    mean_interval_days: float | None = None
    interval_mad_days: float | None = None
    mean_delta_v_m_s: float
    delta_v_mad_m_s: float
    type_distribution: dict[str, int] = Field(default_factory=dict)
    last_epoch: datetime
    updated_at: datetime | None = None


@router.get("/maneuvers", response_model=list[ManeuverResponse], summary="Detected maneuvers")
async def get_maneuvers(
    object_id: str | None = Query(default=None, description="Filter to one object"),
    maneuver_type: str | None = Query(default=None, description="Exact purpose class"),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=5000),
    _subject: Subject = Depends(requires(DataDomain.MANEUVER_INTEL, Action.QUERY)),
) -> list[dict[str, Any]]:
    return await query_maneuvers(
        object_id=object_id,
        maneuver_type=maneuver_type,
        min_confidence=min_confidence,
        limit=limit,
    )


@router.get(
    "/maneuvers/baselines",
    response_model=list[BaselineResponse],
    summary="Per-object behavioral baselines",
)
async def get_baselines(
    limit: int = Query(default=200, ge=1, le=1000),
    _subject: Subject = Depends(requires(DataDomain.MANEUVER_INTEL, Action.READ)),
) -> list[dict[str, Any]]:
    return await query_baselines(limit=limit)
