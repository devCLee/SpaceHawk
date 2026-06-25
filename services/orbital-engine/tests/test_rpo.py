"""Co-planar RPO screening + alert de-duplication (feature #12).

Pure-function tests: synthetic element rows exercise the co-planar/co-altitude
gates, severity tiering, ranking, and the RpoMonitor's new/escalated emission.
"""

from __future__ import annotations

from typing import Any

from orbital_engine.alerts import RpoMonitor
from orbital_engine.config import Settings
from orbital_engine.domain.conjunction import ConjunctionSeverity
from orbital_engine.rpo import coplanarity, raan_delta_deg, screen_rpo

# A ~700 km sun-synchronous protected asset (KOMPSAT-like geometry).
PROTECTED = {
    "object_id": "SH:ASSET",
    "norad_cat_id": 100,
    "object_name": "KOMPSAT-5",
    "inclination": 97.6,
    "ra_of_asc_node": 120.0,
    "semimajor_axis_km": 7080.0,
}


def _threat(oid: str, *, inc: float, raan: float, sma: float, name: str = "THREAT", norad: int = 200):
    return {
        "object_id": oid,
        "norad_cat_id": norad,
        "object_name": name,
        "inclination": inc,
        "ra_of_asc_node": raan,
        "semimajor_axis_km": sma,
    }


def test_raan_delta_wraps_around_360() -> None:
    assert raan_delta_deg(10.0, 350.0) == 20.0
    assert raan_delta_deg(120.0, 121.0) == 1.0


def test_coplanarity_zero_outside_gate_and_peaks_when_aligned() -> None:
    assert coplanarity(0.0, 0.0, 1.0, 5.0) == 1.0
    assert coplanarity(2.0, 0.0, 1.0, 5.0) == 0.0  # inclination outside gate
    assert 0.0 < coplanarity(0.5, 2.5, 1.0, 5.0) < 1.0


def test_coplanar_co_altitude_threat_flagged_high() -> None:
    # Nearly identical plane + altitude => tight => HIGH.
    threat = _threat("SH:T1", inc=97.6, raan=120.1, sma=7080.5)
    events = screen_rpo([PROTECTED], [threat], Settings())
    assert len(events) == 1
    assert events[0].severity == ConjunctionSeverity.HIGH
    assert events[0].id == "RPO:SH:ASSET:SH:T1"


def test_different_plane_not_flagged() -> None:
    # Same altitude, very different node => not co-planar => no event.
    threat = _threat("SH:T2", inc=97.6, raan=200.0, sma=7080.0)
    assert screen_rpo([PROTECTED], [threat], Settings()) == []


def test_different_altitude_not_flagged() -> None:
    # Co-planar but 500 km higher => outside the SMA gate.
    threat = _threat("SH:T3", inc=97.6, raan=120.0, sma=7580.0)
    assert screen_rpo([PROTECTED], [threat], Settings()) == []


def test_loose_coplanar_is_mod_tier() -> None:
    # Inside the gates but not inside half of every gate => MOD, not HIGH.
    threat = _threat("SH:T4", inc=98.2, raan=123.0, sma=7110.0)
    events = screen_rpo([PROTECTED], [threat], Settings())
    assert len(events) == 1
    assert events[0].severity == ConjunctionSeverity.MOD


def test_protected_asset_does_not_screen_against_itself() -> None:
    assert screen_rpo([PROTECTED], [PROTECTED], Settings()) == []


def test_events_ranked_most_coplanar_first() -> None:
    near = _threat("SH:NEAR", inc=97.61, raan=120.1, sma=7080.0, norad=201)
    far = _threat("SH:FAR", inc=98.3, raan=124.0, sma=7090.0, norad=202)
    events = screen_rpo([PROTECTED], [near, far], Settings())
    assert [e.threat_object_id for e in events] == ["SH:NEAR", "SH:FAR"]


def test_sma_recovered_from_mean_motion() -> None:
    # No semimajor_axis_km column: mean motion recovers a co-altitude threat.
    p: dict[str, Any] = {**PROTECTED}
    del p["semimajor_axis_km"]
    p["mean_motion"] = 14.6
    t = _threat("SH:T5", inc=97.6, raan=120.0, sma=0.0)
    del t["semimajor_axis_km"]
    t["mean_motion"] = 14.6
    assert len(screen_rpo([p], [t], Settings())) == 1


def test_monitor_emits_once_then_on_escalation() -> None:
    monitor = RpoMonitor(Settings())
    threat = _threat("SH:T6", inc=98.2, raan=123.0, sma=7110.0)  # MOD
    events = screen_rpo([PROTECTED], [threat], Settings())
    first = monitor.evaluate(events)
    assert len(first) == 1 and first[0]["type"] == "rpo" and first[0]["severity"] == "MOD"
    # Same geometry next cycle => no repeat alert.
    assert monitor.evaluate(events) == []
    # Threat tightens to HIGH => re-alert on escalation.
    tighter = _threat("SH:T6", inc=97.6, raan=120.1, sma=7080.2)
    escalated = monitor.evaluate(screen_rpo([PROTECTED], [tighter], Settings()))
    assert len(escalated) == 1 and escalated[0]["severity"] == "HIGH"
