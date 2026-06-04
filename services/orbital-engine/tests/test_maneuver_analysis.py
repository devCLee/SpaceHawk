"""Δv / RIC decomposition + rule-based purpose classification (feature #11).

Pure-function tests: synthetic Maneuver records exercise each Δv component and
every classification branch deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbital_engine.config import Settings
from orbital_engine.domain.maneuver import Maneuver, ManeuverType
from orbital_engine.maneuver import detect_maneuvers
from orbital_engine.maneuver_analysis import (
    classify_maneuver,
    classify_type,
    estimate_delta_v,
    orbital_speed_km_s,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)
A_ISS = 6790.0  # ~ISS semi-major axis [km]


def _mv(**over) -> Maneuver:
    base = {
        "id": "MNV:test",
        "object_id": "SH:25544",
        "object_name": "ISS",
        "epoch_before": BASE,
        "epoch_after": BASE + timedelta(days=1),
        "detected_epoch": BASE + timedelta(hours=12),
        "delta_sma_km": 0.0,
        "delta_ecc": 0.0,
        "delta_inc_deg": 0.0,
        "delta_raan_deg": 0.0,
        "detection_statistic": 50.0,
        "confidence": 1.0,
        "sma_before_km": A_ISS,
        "inclination_deg": 51.6,
    }
    base.update(over)
    return Maneuver(**base)


def test_orbital_speed_matches_leo() -> None:
    assert 7.5 < orbital_speed_km_s(A_ISS) < 7.8


def test_in_track_dv_tracks_sma_change() -> None:
    # A +10 km raise at ISS altitude is a few m/s, prograde (positive in-track).
    dv = estimate_delta_v(_mv(delta_sma_km=10.0))
    assert dv.in_track > 0.0
    assert 4.0 < dv.total < 8.0
    assert abs(dv.cross_track) < 1e-6 and abs(dv.radial) < 1e-6


def test_cross_track_dv_from_plane_change() -> None:
    dv = estimate_delta_v(_mv(delta_inc_deg=0.1))
    # v * 0.1deg ~ 7.66 km/s * 0.001745 rad * 1000 ~ 13 m/s.
    assert 10.0 < abs(dv.cross_track) < 16.0
    assert abs(dv.in_track) < 1e-6


def test_radial_dv_from_eccentricity_change() -> None:
    dv = estimate_delta_v(_mv(delta_ecc=0.01))
    assert 30.0 < abs(dv.radial) < 45.0


def test_missing_sma_yields_zero_dv() -> None:
    dv = estimate_delta_v(_mv(sma_before_km=None))
    assert dv.total == 0.0


def test_classify_station_keeping() -> None:
    # Tiny raise -> Δv below the station-keeping floor.
    m = classify_maneuver(_mv(delta_sma_km=0.6), Settings())
    assert m.maneuver_type == ManeuverType.STATION_KEEPING


def test_classify_orbit_raise_and_lower() -> None:
    assert classify_maneuver(_mv(delta_sma_km=10.0), Settings()).maneuver_type == ManeuverType.ORBIT_RAISE
    assert classify_maneuver(_mv(delta_sma_km=-10.0), Settings()).maneuver_type == ManeuverType.ORBIT_LOWER


def test_classify_phasing_when_in_track_but_small_sma() -> None:
    # In-track dominated, above station-keeping, below the raise/lower ΔSMA gate.
    s = Settings(maneuver_station_keeping_dv_m_s=0.1, maneuver_orbit_change_min_dsma_km=5.0)
    assert classify_type(estimate_delta_v(_mv(delta_sma_km=1.0)), 1.0, s) == ManeuverType.PHASING


def test_classify_plane_change_is_unknown() -> None:
    # Cross-track dominant: outside the single-object operational set.
    assert classify_maneuver(_mv(delta_inc_deg=0.5), Settings()).maneuver_type == ManeuverType.UNKNOWN


def test_classify_maneuver_enriches_record() -> None:
    m = classify_maneuver(_mv(delta_sma_km=10.0), Settings())
    assert m.delta_v_m_s is not None and m.delta_v_m_s > 0.0
    assert m.ric_in_track_m_s is not None
    # Serialized type is a plain enum value string (DB-bindable).
    assert m.model_dump(mode="python")["maneuver_type"] == "ORBIT_RAISE"


def test_detection_pipeline_classifies_each_detection() -> None:
    # Detection now flows through classification: an injected raise is ORBIT_RAISE.
    smas = [A_ISS, A_ISS - 0.1, A_ISS - 0.2, A_ISS + 9.8, A_ISS + 9.7, A_ISS + 9.6]
    rows = [
        {
            "object_id": "SH:25544",
            "object_name": "ISS",
            "norad_cat_id": 25544,
            "epoch": BASE + timedelta(days=i),
            "semimajor_axis_km": s,
            "eccentricity": 0.0006,
            "inclination": 51.6,
            "ra_of_asc_node": 32.0,
        }
        for i, s in enumerate(smas)
    ]
    maneuvers = detect_maneuvers(rows, Settings())
    assert len(maneuvers) == 1
    assert maneuvers[0].maneuver_type == ManeuverType.ORBIT_RAISE
    assert maneuvers[0].delta_v_m_s and maneuvers[0].delta_v_m_s > 1.0
