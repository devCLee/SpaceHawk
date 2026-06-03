"""The slice's one rule-based alert: object enters a region of interest.

Deliberately trivial (dev-plan Stage 1 / P0-THIN-SLICE-PLAN §2): it exists to
exercise the SSE fan-out path end-to-end, not to be operationally meaningful.
Stage 4 replaces this with real conjunction screening + trust-calibrated tiers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from orbital_engine.config import Settings


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
