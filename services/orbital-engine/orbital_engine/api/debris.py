"""Debris catalog + risk endpoints consumed by the web BFF (debris-viz/risk).

``GET /debris`` returns the tracked-debris subset of the catalog with per-object
risk (the globe layer + popups). ``GET /debris/risk`` adds the population analysis:
counts per risk level, a debris-density-by-altitude-shell profile (the classic
ODPO LEO profile, peaking ~800-1000 km), and the screened debris conjunctions
with their real probability-of-collision (reusing the screening loop's output).

Risk *level* comes from the explainable ``debris_risk`` model (always available);
collision *probability* comes from the engine's SGP4 screening (``estimate_pc``)
surfaced via the conjunctions — the two are deliberately distinct.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from orbital_engine.api.conjunctions import ConjunctionResponse
from orbital_engine.debris_risk import circular_speed_km_s, risk_level, risk_score
from orbital_engine.repository import query_debris, query_debris_conjunctions
from orbital_engine.screening import orbit_altitudes
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires

router = APIRouter(tags=["debris"])


class DebrisObject(BaseModel):
    """One tracked-debris object with derived orbital params + risk."""

    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    country_code: str | None = None
    rcs_size: str | None = None
    inclination: float | None = None
    eccentricity: float | None = None
    period_min: float | None = None
    apoapsis_km: float | None = None
    periapsis_km: float | None = None
    mean_altitude_km: float | None = None
    speed_km_s: float | None = None
    risk_score: float = 0.0
    risk_level: str = "Low"
    tle_line0: str | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None


class ShellBin(BaseModel):
    """Debris count in one 100 km altitude shell (density-by-shell profile)."""

    altitude_km: int
    count: int


class DebrisRiskSummary(BaseModel):
    """Population-level debris risk analysis."""

    total: int
    by_level: dict[str, int] = Field(default_factory=dict)
    density_by_shell: list[ShellBin] = Field(default_factory=list)
    conjunctions: list[ConjunctionResponse] = Field(default_factory=list)


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    """Derive mean altitude, speed and the risk score/level for one debris row."""
    apo = row.get("apoapsis_km")
    peri = row.get("periapsis_km")
    mm = row.get("mean_motion")
    ecc = row.get("eccentricity")
    if (apo is None or peri is None) and mm is not None and ecc is not None:
        apo, peri = orbit_altitudes(float(mm), float(ecc))
    mean_alt = (float(apo) + float(peri)) / 2.0 if apo is not None and peri is not None else None
    speed = circular_speed_km_s(mean_alt) if mean_alt is not None else None
    score = (
        risk_score(mean_alt, speed, row.get("rcs_size"))
        if mean_alt is not None and speed is not None
        else 0.0
    )
    return {
        **row,
        "apoapsis_km": apo,
        "periapsis_km": peri,
        "mean_altitude_km": mean_alt,
        "speed_km_s": speed,
        "risk_score": score,
        "risk_level": risk_level(score),
    }


@router.get("/debris", response_model=list[DebrisObject], summary="Tracked debris + risk")
async def get_debris(
    limit: int = Query(default=2000, ge=1, le=20000),
    offset: int = Query(default=0, ge=0),
    _subject: Subject = Depends(requires(DataDomain.CATALOG, Action.QUERY)),
) -> list[dict[str, Any]]:
    return [_enrich(row) for row in await query_debris(limit=limit, offset=offset)]


@router.get("/debris/risk", response_model=DebrisRiskSummary, summary="Debris risk analysis")
async def get_debris_risk(
    _subject: Subject = Depends(requires(DataDomain.SCREENING, Action.QUERY)),
) -> DebrisRiskSummary:
    rows = [_enrich(row) for row in await query_debris(limit=20000)]
    by_level: dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    shells: dict[int, int] = {}
    for row in rows:
        by_level[row["risk_level"]] = by_level.get(row["risk_level"], 0) + 1
        alt = row.get("mean_altitude_km")
        if alt is not None:
            band = int(alt // 100) * 100
            shells[band] = shells.get(band, 0) + 1
    density = [ShellBin(altitude_km=k, count=shells[k]) for k in sorted(shells)]
    conjunctions = await query_debris_conjunctions(limit=200)
    return DebrisRiskSummary(
        total=len(rows),
        by_level=by_level,
        density_by_shell=density,
        conjunctions=conjunctions,  # type: ignore[arg-type]
    )
