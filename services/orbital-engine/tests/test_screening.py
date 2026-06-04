"""Conjunction screening: gate, closest approach, Pc, and orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from sgp4.api import Satrec, jday

from orbital_engine.config import Settings
from orbital_engine.domain.conjunction import ConjunctionSeverity, estimate_pc
from orbital_engine.screening import (
    apogee_perigee_gate,
    closest_approach,
    orbit_altitudes,
    screen_objects,
)

# Real ISS element set (also used by the Space-Track fixtures).
ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"
NOW = datetime(2024, 3, 11, 0, 0, 0, tzinfo=UTC)


def _row(object_id: str, norad: int, *, mean_motion: float = 15.50079139, ecc: float = 0.0006008):
    return {
        "object_id": object_id,
        "norad_cat_id": norad,
        "object_name": f"OBJ {norad}",
        "mean_motion": mean_motion,
        "eccentricity": ecc,
        "tle_line1": ISS_L1,
        "tle_line2": ISS_L2,
    }


def test_orbit_altitudes_recovers_iss_band() -> None:
    apo, peri = orbit_altitudes(15.50079139, 0.0006008)
    assert 380.0 < peri < apo < 430.0


def test_apogee_perigee_gate_prunes_disjoint_shells() -> None:
    # Two ~400 km bands overlap; a 400 km band and a 36,000 km band do not.
    assert apogee_perigee_gate(420, 400, 410, 405, pad_km=10) is True
    assert apogee_perigee_gate(420, 400, 35800, 35780, pad_km=10) is False
    # The pad can bridge a narrow gap.
    assert apogee_perigee_gate(500, 480, 470, 460, pad_km=20) is True
    assert apogee_perigee_gate(500, 480, 470, 460, pad_km=1) is False


def test_closest_approach_of_identical_orbits_is_zero() -> None:
    sat = Satrec.twoline2rv(ISS_L1, ISS_L2)
    jd0, fr0 = jday(NOW.year, NOW.month, NOW.day, NOW.hour, NOW.minute, NOW.second)
    offset, miss, rel = closest_approach(sat, sat, jd0, fr0, window_sec=7200.0, step_sec=600.0)
    assert miss < 1e-6
    assert rel is not None and rel < 1e-6


def test_estimate_pc_is_bounded_and_monotonic() -> None:
    near = estimate_pc(0.0, 1.0, 0.05)
    far = estimate_pc(5.0, 1.0, 0.05)
    assert 0.0 <= far < near <= 1.0
    assert estimate_pc(1.0, 0.0, 0.05) == 0.0  # zero sigma guarded


def test_screen_objects_flags_co_located_pair() -> None:
    settings = Settings(conjunction_screen_window_hours=2.0, conjunction_screen_step_sec=600)
    conjunctions = screen_objects([_row("A", 25544), _row("B", 25545)], settings, now=NOW)
    assert len(conjunctions) == 1
    c = conjunctions[0]
    assert c.miss_distance_km < 1e-6
    assert c.severity == ConjunctionSeverity.HIGH


def test_screen_objects_prunes_non_overlapping_shells() -> None:
    settings = Settings(conjunction_screen_window_hours=2.0, conjunction_screen_step_sec=600)
    leo = _row("A", 25544)
    geo = _row("C", 99999, mean_motion=1.0027, ecc=0.0001)  # ~GEO altitude band
    assert screen_objects([leo, geo], settings, now=NOW) == []


def test_screen_objects_protected_only_pairs_against_watchlist() -> None:
    settings = Settings(
        conjunction_screen_window_hours=2.0,
        conjunction_screen_step_sec=600,
        protected_norad_ids=[25544],
    )
    rows = [_row("A", 25544), _row("B", 25545), _row("D", 25546)]
    conjunctions = screen_objects(rows, settings, now=NOW)
    # 25544 vs 25545 and 25544 vs 25546 — but not 25545 vs 25546.
    assert len(conjunctions) == 2
    assert all(c.primary_norad_cat_id == 25544 for c in conjunctions)
