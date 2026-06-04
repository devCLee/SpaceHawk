"""The slice's one rule-based alert: object enters a region of interest.

Deliberately trivial (dev-plan Stage 1 / P0-THIN-SLICE-PLAN §2): it exists to
exercise the SSE fan-out path end-to-end, not to be operationally meaningful.
Stage 4 replaces this with real conjunction screening + trust-calibrated tiers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from orbital_engine.config import Settings
from orbital_engine.domain.conjunction import Conjunction, ConjunctionSeverity
from orbital_engine.rpo import RpoEvent


class RegionMonitor:
    """Emits an alert when an object transitions from outside to inside the ROI."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._inside: set[str] = set()

    def _in_roi(self, lat: float, lon: float) -> bool:
        return (
            self._s.roi_lat_min <= lat <= self._s.roi_lat_max
            and self._s.roi_lon_min <= lon <= self._s.roi_lon_max
        )

    def evaluate(self, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return alert dicts for objects that just entered the ROI."""
        now_inside: set[str] = set()
        alerts: list[dict[str, Any]] = []
        for st in states:
            oid = st.get("object_id")
            if oid is None:
                continue
            if self._in_roi(st["lat_deg"], st["lon_deg"]):
                now_inside.add(oid)
                if oid not in self._inside:
                    alerts.append(
                        {
                            "type": "region-entry",
                            "object_id": oid,
                            "object_name": st.get("object_name"),
                            "lat_deg": st["lat_deg"],
                            "lon_deg": st["lon_deg"],
                            "alt_km": st["alt_km"],
                            "ts": datetime.now(UTC).isoformat(),
                            "message": (
                                f"{st.get('object_name') or oid} entered the region of interest"
                            ),
                        }
                    )
        self._inside = now_inside
        return alerts


# Tier ordering for "is this worse than what we already alerted on?" comparisons.
_SEVERITY_RANK: dict[str, int] = {
    ConjunctionSeverity.LOW.value: 0,
    ConjunctionSeverity.MOD.value: 1,
    ConjunctionSeverity.HIGH.value: 2,
}


class ConjunctionAlerter:
    """Turns screened/CDM conjunctions into alerts, de-duplicated per event.

    Mirrors :class:`RegionMonitor`: only emits when a conjunction is *new* or has
    *escalated* to a higher tier since it was last alerted, so the analyst is not
    spammed every screening cycle. Conjunctions below the configured minimum tier
    are ignored entirely (the trust-calibrated floor that attacks the false-
    positive drain, roadmap O2/O4).
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._emitted: dict[str, str] = {}  # conjunction id -> last emitted severity

    def _min_rank(self) -> int:
        return _SEVERITY_RANK.get(self._s.conjunction_alert_min_severity, 1)

    def _to_alert(self, c: Conjunction) -> dict[str, Any]:
        tca = c.tca.isoformat() if isinstance(c.tca, datetime) else str(c.tca)
        return {
            "id": c.id,
            "type": "conjunction",
            "severity": c.severity,
            "object_id": c.primary_object_id,
            "conjunction_id": c.id,
            "message": (
                f"{c.primary_name} ↔ {c.secondary_name}: "
                f"{c.miss_distance_km:.2f} km miss @ {tca}"
            ),
            "payload": c.model_dump(mode="json"),
            "ts": datetime.now(UTC).isoformat(),
        }

    def evaluate(self, conjunctions: list[Conjunction]) -> list[dict[str, Any]]:
        """Return alert dicts for conjunctions that are new or have escalated."""
        alerts: list[dict[str, Any]] = []
        for c in conjunctions:
            rank = _SEVERITY_RANK.get(c.severity, 0)
            if rank < self._min_rank():
                continue
            prev = self._emitted.get(c.id)
            if prev is None or rank > _SEVERITY_RANK.get(prev, -1):
                alerts.append(self._to_alert(c))
                self._emitted[c.id] = c.severity
        return alerts


class RpoMonitor:
    """Turns co-planar RPO events into alerts, de-duplicated per (asset, threat) pair.

    Mirrors :class:`ConjunctionAlerter`: only emits when an RPO geometry is *new*
    or has *escalated* tier since last alerted, so a persistently co-planar threat
    does not re-alert every screening cycle (Stage 6 feature #12 → Stage-4 alert
    center). RPO is a heightened-sensitivity signal, so — unlike conjunctions —
    there is no minimum-tier floor: every flagged event is worth an analyst's eye.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._emitted: dict[str, str] = {}  # rpo event id -> last emitted severity

    def _to_alert(self, e: RpoEvent) -> dict[str, Any]:
        return {
            "id": e.id,
            "type": "rpo",
            "severity": e.severity.value if isinstance(e.severity, ConjunctionSeverity) else e.severity,
            "object_id": e.protected_object_id,
            "conjunction_id": None,
            "message": (
                f"Co-planar RPO: {e.threat_name} shadowing {e.protected_name} "
                f"(Δi={e.delta_inc_deg:.2f}°, ΔΩ={e.delta_raan_deg:.2f}°, "
                f"Δa={e.delta_sma_km:.1f} km)"
            ),
            "payload": {
                "protected_object_id": e.protected_object_id,
                "protected_norad_cat_id": e.protected_norad_cat_id,
                "protected_name": e.protected_name,
                "threat_object_id": e.threat_object_id,
                "threat_norad_cat_id": e.threat_norad_cat_id,
                "threat_name": e.threat_name,
                "delta_inc_deg": e.delta_inc_deg,
                "delta_raan_deg": e.delta_raan_deg,
                "delta_sma_km": e.delta_sma_km,
                "coplanarity": e.coplanarity,
                "severity": e.severity.value if isinstance(e.severity, ConjunctionSeverity) else e.severity,
            },
            "ts": datetime.now(UTC).isoformat(),
        }

    def evaluate(self, events: list[RpoEvent]) -> list[dict[str, Any]]:
        """Return alert dicts for RPO events that are new or have escalated."""
        alerts: list[dict[str, Any]] = []
        for e in events:
            sev = e.severity.value if isinstance(e.severity, ConjunctionSeverity) else e.severity
            rank = _SEVERITY_RANK.get(sev, 0)
            prev = self._emitted.get(e.id)
            if prev is None or rank > _SEVERITY_RANK.get(prev, -1):
                alerts.append(self._to_alert(e))
                self._emitted[e.id] = sev
        return alerts
