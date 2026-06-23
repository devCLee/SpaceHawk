"""Observer-based pass prediction over 대전 KARI (R2).

Pins the topocentric transform (overhead -> ~90 deg, horizon -> ~0 deg) and the
pass detector (a real LEO TLE over a multi-hour window yields well-formed passes;
a GEO object below the mask and degenerate windows yield none / [] without
crashing; the min-elevation mask filters low passes).

``orbital_engine.reports.passes`` is loaded directly from its file path so the
report package's ``__init__`` (currently out of sync — its ``assembler`` imports
schema names this branch's R1 ``schemas.py`` does not yet define) is not executed.
``passes`` itself only depends on ``orbital_engine.propagation.*``.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from orbital_engine.propagation.coordinates import teme_to_ecef
from orbital_engine.propagation.sgp4_service import propagate_tle

_PASSES_PATH = Path(__file__).resolve().parents[1] / "orbital_engine" / "reports" / "passes.py"
_MOD_NAME = "orbital_engine_reports_passes"
_spec = importlib.util.spec_from_file_location(_MOD_NAME, _PASSES_PATH)
assert _spec is not None and _spec.loader is not None
passes = importlib.util.module_from_spec(_spec)
# Register before exec so dataclass() can resolve cls.__module__'s namespace
# (needed under `from __future__ import annotations`).
sys.modules[_MOD_NAME] = passes
_spec.loader.exec_module(passes)

KARI = passes.KARI
Observer = passes.Observer
PassGeometry = passes.PassGeometry
ecef_to_topocentric = passes.ecef_to_topocentric
predict_passes = passes.predict_passes

# Real ISS TLE (the engine's propagation tests use this set).
ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"

# A near-equatorial GEO (period ~1436 min) parked on the far side of Earth from
# KARI (mean anomaly 180 deg => sub-longitude ~opposite KARI): its elevation from
# 대전 stays below the local horizon for the whole short window — never rises.
GEO_L1 = "1 19548U 88091B   24070.50000000 -.00000100  00000-0  00000-0 0  9990"
GEO_L2 = "2 19548   0.0500  80.0000 0001000   0.0000 180.0000  1.00270000 99999"


def _epoch() -> datetime:
    # ISS TLE epoch 2024-070 (10 Mar 2024) — propagate near it for valid passes.
    return datetime(2024, 3, 10, 0, 0, 0, tzinfo=UTC)


# --- Topocentric transform sanity -------------------------------------------


def test_overhead_satellite_is_near_zenith() -> None:
    # Place a satellite on the radial straight above KARI: convert the observer
    # to ECEF, push out 600 km along its own position unit vector.
    obs_ecef = passes._observer_ecef(KARI)
    norm = math.sqrt(sum(c * c for c in obs_ecef))
    overhead = tuple(c * (norm + 600.0) / norm for c in obs_ecef)
    az, el, rng = ecef_to_topocentric(overhead, KARI)
    assert el > 89.0
    assert 0.0 <= az < 360.0
    assert abs(rng - 600.0) < 1.0


def test_horizon_satellite_is_near_zero_elevation() -> None:
    # A point on the local horizon: start at the observer, step out along local
    # East (perpendicular to Up), far enough to clear the geometry.
    lon = math.radians(KARI.lon_deg)
    east = (-math.sin(lon), math.cos(lon), 0.0)
    obs = passes._observer_ecef(KARI)
    horizon = tuple(obs[i] + east[i] * 500.0 for i in range(3))
    _, el, rng = ecef_to_topocentric(horizon, KARI)
    assert abs(el) < 1.0
    assert rng > 0.0


def test_topocentric_azimuth_and_range_bounds() -> None:
    state = propagate_tle(ISS_L1, ISS_L2, _epoch())
    assert state is not None
    sat_ecef = teme_to_ecef(tuple(state["teme_position_km"]), state["gmst_rad"])
    az, el, rng = ecef_to_topocentric(sat_ecef, KARI)
    assert 0.0 <= az < 360.0
    assert -90.0 <= el <= 90.0
    assert rng > 0.0


# --- Pass detection ---------------------------------------------------------


def test_leo_object_produces_well_formed_passes() -> None:
    start = _epoch()
    end = start + timedelta(hours=12)
    found = predict_passes((ISS_L1, ISS_L2), KARI, start, end, step_s=30.0, min_elevation_deg=0.0)

    assert len(found) >= 1
    for p in found:
        assert isinstance(p, PassGeometry)
        assert start <= p.aos <= p.closest_time <= p.los <= end
        assert 0.0 <= p.elevation_deg <= 90.0
        assert 0.0 <= p.azimuth_deg < 360.0
        assert p.closest_distance_km > 0.0


def test_closest_distance_is_minimum_over_the_pass() -> None:
    start = _epoch()
    end = start + timedelta(hours=12)
    found = predict_passes((ISS_L1, ISS_L2), KARI, start, end, step_s=30.0, min_elevation_deg=0.0)
    assert found
    p = found[0]
    # The refined closest point should be the max-elevation sample of the pass.
    n = int((p.los - p.aos).total_seconds() // 30) + 1
    sampled_max_el = max(
        passes._look_angle(ISS_L1, ISS_L2, KARI, p.aos + timedelta(seconds=30 * k))[1]
        for k in range(n)
    )
    assert p.elevation_deg >= sampled_max_el - 0.01


def test_min_elevation_mask_filters_low_passes() -> None:
    start = _epoch()
    end = start + timedelta(hours=12)
    low = predict_passes((ISS_L1, ISS_L2), KARI, start, end, step_s=30.0, min_elevation_deg=0.0)
    high = predict_passes((ISS_L1, ISS_L2), KARI, start, end, step_s=30.0, min_elevation_deg=40.0)
    # Raising the mask never adds passes and drops the low ones.
    assert len(high) <= len(low)
    for p in high:
        assert p.elevation_deg >= 40.0


def test_geo_object_below_mask_yields_no_passes() -> None:
    # Far-side GEO never rises above the horizon over a short window — even with a
    # zero-degree mask it produces zero passes and does not crash.
    start = _epoch()
    end = start + timedelta(minutes=30)
    found = predict_passes((GEO_L1, GEO_L2), KARI, start, end, step_s=30.0, min_elevation_deg=0.0)
    assert found == []


# --- Degenerate windows -----------------------------------------------------


def test_empty_window_returns_empty() -> None:
    t = _epoch()
    assert predict_passes((ISS_L1, ISS_L2), KARI, t, t) == []


def test_reversed_window_returns_empty() -> None:
    start = _epoch()
    end = start - timedelta(hours=1)
    assert predict_passes((ISS_L1, ISS_L2), KARI, start, end) == []


def test_non_positive_step_returns_empty() -> None:
    start = _epoch()
    end = start + timedelta(hours=1)
    assert predict_passes((ISS_L1, ISS_L2), KARI, start, end, step_s=0.0) == []


def test_custom_observer_is_honored() -> None:
    # A pure compute path: a custom Observer is accepted (no reliance on KARI).
    obs = Observer(lat_deg=0.0, lon_deg=0.0, alt_km=0.0)
    start = _epoch()
    end = start + timedelta(hours=3)
    found = predict_passes((ISS_L1, ISS_L2), obs, start, end, min_elevation_deg=0.0)
    for p in found:
        assert 0.0 <= p.azimuth_deg < 360.0
