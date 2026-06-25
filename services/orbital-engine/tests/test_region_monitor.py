"""The trivial region-entry alert rule."""

from __future__ import annotations

from orbital_engine.alerts import RegionMonitor
from orbital_engine.config import Settings


def _state(object_id: str, lat: float, lon: float) -> dict:
    return {"object_id": object_id, "object_name": object_id, "lat_deg": lat, "lon_deg": lon, "alt_km": 500.0}


def _monitor() -> RegionMonitor:
    # Default ROI is the Korean theatre box (lat 33–43, lon 124–132).
    return RegionMonitor(Settings())


def test_fires_on_entry() -> None:
    monitor = _monitor()
    alerts = monitor.evaluate([_state("A", 37.5, 127.0)])
    assert len(alerts) == 1
    assert alerts[0]["type"] == "region-entry"
    assert alerts[0]["object_id"] == "A"


def test_no_alert_outside_roi() -> None:
    assert _monitor().evaluate([_state("A", 0.0, 0.0)]) == []


def test_does_not_refire_while_inside() -> None:
    monitor = _monitor()
    monitor.evaluate([_state("A", 37.5, 127.0)])
    # Still inside on the next tick -> no new alert.
    assert monitor.evaluate([_state("A", 38.0, 128.0)]) == []


def test_refires_after_leaving_and_returning() -> None:
    monitor = _monitor()
    monitor.evaluate([_state("A", 37.5, 127.0)])
    monitor.evaluate([_state("A", 0.0, 0.0)])  # left the ROI
    assert len(monitor.evaluate([_state("A", 37.5, 127.0)])) == 1
