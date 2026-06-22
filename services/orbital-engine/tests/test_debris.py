"""Debris ingestion + risk scoring (pure, no network/DB)."""

from __future__ import annotations

import pytest

from orbital_engine.api.debris import _enrich
from orbital_engine.config import Settings
from orbital_engine.debris_risk import (
    circular_speed_km_s,
    density_factor,
    risk_level,
    risk_score,
    size_factor,
    velocity_factor,
)
from orbital_engine.domain.space_object import ObjectType
from orbital_engine.ingestion import celestrak
from orbital_engine.ingestion.celestrak import fetch_celestrak_debris, normalize

# A Cosmos-2251 fragment (debris group member): name carries no OBJECT_TYPE in GP.
DEB_L1 = "1 34427U 93036SX  24070.50000000  .00010000  00000-0  20000-3 0  9990"
DEB_L2 = "2 34427  74.0000 100.0000 0050000  90.0000 270.0000 14.20000000123456"
DEB_TLE = f"COSMOS 2251 DEB\n{DEB_L1}\n{DEB_L2}\n"
DEB_OMM = {
    "OBJECT_NAME": "COSMOS 2251 DEB",
    "OBJECT_ID": "1993-036SX",
    "NORAD_CAT_ID": 34427,
    "EPOCH": "2024-03-10T12:00:00.000",
    "MEAN_MOTION": 14.2,
    "ECCENTRICITY": 0.005,
    "INCLINATION": 74.0,
    "RA_OF_ASC_NODE": 100.0,
    "ARG_OF_PERICENTER": 90.0,
    "MEAN_ANOMALY": 270.0,
    "CLASSIFICATION_TYPE": "U",
}


# --- Risk model -------------------------------------------------------------


def test_density_factor_peaks_in_primary_leo_band() -> None:
    assert density_factor(850.0) == 1.0  # ~800-1000 km densest shell
    assert density_factor(1400.0) == 0.8  # secondary peak
    assert density_factor(400.0) == 0.2  # drag clears it fast
    assert density_factor(3000.0) == 0.15  # MEO, sparse


def test_velocity_and_size_factors_clamp() -> None:
    assert velocity_factor(7.5) == pytest.approx(0.9375)
    assert velocity_factor(100.0) == 1.0
    assert size_factor("LARGE") == 1.0
    assert size_factor(None) == 0.5  # CelesTrak-GP common case


def test_risk_score_and_level_match_documented_examples() -> None:
    # Large fragment at ~850 km -> Critical.
    big_leo = risk_score(850.0, circular_speed_km_s(850.0), "LARGE")
    assert big_leo >= 70.0
    assert risk_level(big_leo) == "Critical"
    # Decaying small fragment at ~400 km -> Low.
    decaying = risk_score(400.0, circular_speed_km_s(400.0), "SMALL")
    assert risk_level(decaying) == "Low"


def test_risk_level_thresholds() -> None:
    assert risk_level(70.0) == "Critical"
    assert risk_level(69.9) == "High"
    assert risk_level(45.0) == "High"
    assert risk_level(20.0) == "Medium"
    assert risk_level(19.9) == "Low"


# --- Enrichment (derives apsis/speed/risk from a raw debris row) -------------


def test_enrich_derives_altitude_speed_and_risk_from_mean_elements() -> None:
    row = {
        "object_id": "SH:CAT:000034427",
        "object_name": "COSMOS 2251 DEB",
        "mean_motion": 14.2,
        "eccentricity": 0.005,
        "rcs_size": None,
        "apoapsis_km": None,
        "periapsis_km": None,
    }
    out = _enrich(row)
    assert out["mean_altitude_km"] is not None and out["mean_altitude_km"] > 0
    assert out["speed_km_s"] is not None and 6.0 < out["speed_km_s"] < 8.0
    assert out["risk_level"] in {"Low", "Medium", "High", "Critical"}
    assert 0.0 <= out["risk_score"] <= 100.0


# --- Ingestion: debris groups stamp object_type=DEBRIS ----------------------


def test_normalize_stamps_debris_object_type() -> None:
    objects = normalize([DEB_OMM], DEB_TLE, default_object_type=ObjectType.DEBRIS)
    assert len(objects) == 1
    assert objects[0].object_type == ObjectType.DEBRIS
    assert objects[0].tle_line1 == DEB_L1


def test_normalize_defaults_unknown_without_override() -> None:
    objects = normalize([DEB_OMM], DEB_TLE)
    assert objects[0].object_type == ObjectType.UNKNOWN


@pytest.mark.asyncio
async def test_fetch_celestrak_debris_empty_when_unconfigured() -> None:
    # No debris groups configured -> no network, empty result.
    settings = Settings(celestrak_debris_groups=[])
    assert await fetch_celestrak_debris(settings) == []


@pytest.mark.asyncio
async def test_fetch_celestrak_debris_fetches_each_group(monkeypatch) -> None:
    # Two groups configured -> two (json+tle) fetches, stamped DEBRIS.
    from tests.test_celestrak_ingest import _FakeClient, _FakeResp

    responses = [
        _FakeResp(200, json_data=[DEB_OMM]),
        _FakeResp(200, text=DEB_TLE),
        _FakeResp(200, json_data=[DEB_OMM]),
        _FakeResp(200, text=DEB_TLE),
    ]
    monkeypatch.setattr(
        celestrak.httpx, "AsyncClient", lambda *a, **k: _FakeClient(responses)
    )
    settings = Settings(celestrak_debris_groups=["cosmos-2251-debris", "iridium-33-debris"])
    objects = await fetch_celestrak_debris(settings)
    # Same NORAD across both groups -> the function concatenates (merge.py dedups
    # later by USOID); both are stamped DEBRIS.
    assert len(objects) == 2
    assert all(o.object_type == ObjectType.DEBRIS for o in objects)
