"""Co-planar RPO monitoring of protected assets (Stage 6 feature #12, dev-plan §5).

Rendezvous & Proximity Operations (RPO) begin with a co-orbital approach: a threat
object shares a protected asset's orbital *plane* (small inclination and RAAN
difference) at a similar *altitude* (semi-major axis). Those are the conditions
under which one object can close on and station-keep near another, so they are the
screen the roadmap names (P2a #4 — "co-planar RPO monitoring of ROK assets,
Δi/ΔRAAN gates").

This module is pure element-space geometry (Δi / ΔRAAN / Δa), matching the
screening module's approach — no PostGIS dependency. (PostGIS is reserved for
later footprint/volumetric work, dev-plan §4.4.) ``screen_rpo`` pairs each
protected asset against the rest of the catalog; the ``RpoMonitor`` in
``alerts`` turns the flagged events into alert-center alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.conjunction import ConjunctionSeverity
from orbital_engine.domain.maneuver import semimajor_axis_km


def raan_delta_deg(raan_a: float, raan_b: float) -> float:
    """Smallest separation between two right-ascensions of ascending node [0,180]."""
    d = abs(raan_a - raan_b) % 360.0
    return min(d, 360.0 - d)


def coplanarity(delta_inc_deg: float, delta_raan_deg: float, inc_gate: float, raan_gate: float) -> float:
    """A 0..1 co-planarity score: 1 when perfectly aligned, 0 at the gate edges.

    Linear in each axis and combined multiplicatively, so the score only stays
    high when *both* the inclination and the node are close — the actual
    co-planar condition. Outside either gate the score is 0.
    """
    if delta_inc_deg > inc_gate or delta_raan_deg > raan_gate or inc_gate <= 0 or raan_gate <= 0:
        return 0.0
    return (1.0 - delta_inc_deg / inc_gate) * (1.0 - delta_raan_deg / raan_gate)


def _sma_of(row: dict[str, Any]) -> float | None:
    sma = row.get("semimajor_axis_km")
    mm = row.get("mean_motion")
    if sma is not None:
        return float(sma)
    if mm:
        return semimajor_axis_km(float(mm))
    return None


@dataclass(frozen=True)
class RpoEvent:
    """One co-planar, co-altitude threat geometry against a protected asset."""

    protected_object_id: str
    protected_norad_cat_id: int | None
    protected_name: str
    threat_object_id: str
    threat_norad_cat_id: int | None
    threat_name: str
    delta_inc_deg: float
    delta_raan_deg: float
    delta_sma_km: float
    coplanarity: float
    severity: ConjunctionSeverity

    @property
    def id(self) -> str:
        """Stable id per ordered (protected, threat) pair — re-screens upsert."""
        return f"RPO:{self.protected_object_id}:{self.threat_object_id}"


def _severity_for(
    delta_inc: float, delta_raan: float, delta_sma: float, settings: Settings
) -> ConjunctionSeverity:
    """HIGH when well inside half of every gate (tight, near-station-keeping); else MOD."""
    tight = (
        delta_inc <= settings.rpo_inclination_gate_deg / 2.0
        and delta_raan <= settings.rpo_raan_gate_deg / 2.0
        and delta_sma <= settings.rpo_sma_gate_km / 2.0
    )
    return ConjunctionSeverity.HIGH if tight else ConjunctionSeverity.MOD


def _screen_pair(
    protected: dict[str, Any], threat: dict[str, Any], settings: Settings
) -> RpoEvent | None:
    sma_p, sma_t = _sma_of(protected), _sma_of(threat)
    if sma_p is None or sma_t is None:
        return None
    delta_inc = abs(float(protected.get("inclination") or 0.0) - float(threat.get("inclination") or 0.0))
    delta_raan = raan_delta_deg(
        float(protected.get("ra_of_asc_node") or 0.0), float(threat.get("ra_of_asc_node") or 0.0)
    )
    delta_sma = abs(sma_p - sma_t)
    if delta_sma > settings.rpo_sma_gate_km:
        return None
    score = coplanarity(
        delta_inc, delta_raan, settings.rpo_inclination_gate_deg, settings.rpo_raan_gate_deg
    )
    if score <= 0.0:
        return None
    return RpoEvent(
        protected_object_id=protected["object_id"],
        protected_norad_cat_id=protected.get("norad_cat_id"),
        protected_name=protected.get("object_name") or protected["object_id"],
        threat_object_id=threat["object_id"],
        threat_norad_cat_id=threat.get("norad_cat_id"),
        threat_name=threat.get("object_name") or threat["object_id"],
        delta_inc_deg=delta_inc,
        delta_raan_deg=delta_raan,
        delta_sma_km=delta_sma,
        coplanarity=score,
        severity=_severity_for(delta_inc, delta_raan, delta_sma, settings),
    )


def screen_rpo(
    protected_rows: list[dict[str, Any]],
    other_rows: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[RpoEvent]:
    """Flag co-planar, co-altitude approachers of each protected asset.

    ``protected_rows`` are the watch-list assets; ``other_rows`` is the rest of the
    catalog. Each row needs ``inclination``, ``ra_of_asc_node`` and either
    ``semimajor_axis_km`` or ``mean_motion``. Returns events ranked most-co-planar
    first. A protected asset never screens against itself (filtered by id).
    """
    settings = settings or get_settings()
    events: list[RpoEvent] = []
    for protected in protected_rows:
        for threat in other_rows:
            if threat.get("object_id") == protected.get("object_id"):
                continue
            event = _screen_pair(protected, threat, settings)
            if event is not None:
                events.append(event)
    events.sort(key=lambda e: e.coplanarity, reverse=True)
    return events
