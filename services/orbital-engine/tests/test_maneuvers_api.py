"""Maneuver-intel endpoints (repo monkeypatched, no DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine.api import maneuvers as mnv_api
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.security.tokens import mint_token


def _admin_headers() -> dict[str, str]:
    settings = get_settings()
    token = mint_token(
        {"sub": "operator1", "role": "ADMIN", "service": "JOINT", "clr": "S", "scope": [], "grants": []},
        secret=settings.auth_jwt_secret,
        ttl_sec=300,
    )
    return {"Authorization": f"Bearer {token}"}


client = TestClient(create_app(), headers=_admin_headers())

MANEUVER = {
    "id": "MNV:SH:CAT:000025544:20260601T000000",
    "object_id": "SH:CAT:000025544",
    "norad_cat_id": 25544,
    "object_name": "ISS (ZARYA)",
    "epoch_before": "2026-05-31T00:00:00",
    "epoch_after": "2026-06-01T00:00:00",
    "detected_epoch": "2026-05-31T12:00:00",
    "delta_sma_km": 10.0,
    "delta_ecc": 0.0,
    "delta_inc_deg": 0.0,
    "delta_raan_deg": 0.0,
    "detection_statistic": 50.0,
    "confidence": 0.9,
    "sma_before_km": 6790.0,
    "inclination_deg": 51.6,
    "delta_v_m_s": 5.6,
    "ric_radial_m_s": 0.0,
    "ric_in_track_m_s": 5.6,
    "ric_cross_track_m_s": 0.0,
    "maneuver_type": "ORBIT_RAISE",
    "detected_at": "2026-06-04T00:00:00",
}

BASELINE = {
    "object_id": "SH:CAT:000025544",
    "object_name": "ISS (ZARYA)",
    "sample_count": 6,
    "mean_interval_days": 30.0,
    "interval_mad_days": 1.0,
    "mean_delta_v_m_s": 5.0,
    "delta_v_mad_m_s": 0.3,
    "type_distribution": {"STATION_KEEPING": 6},
    "last_epoch": "2026-06-01T00:00:00",
    "updated_at": "2026-06-04T00:00:00",
}


def test_get_maneuvers_passes_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return [MANEUVER]

    monkeypatch.setattr(mnv_api, "query_maneuvers", fake_query)
    resp = client.get(
        "/maneuvers", params={"object_id": "SH:CAT:000025544", "maneuver_type": "ORBIT_RAISE", "limit": 50}
    )
    assert resp.status_code == 200
    assert captured == {
        "object_id": "SH:CAT:000025544",
        "maneuver_type": "ORBIT_RAISE",
        "min_confidence": None,
        "limit": 50,
    }
    body = resp.json()
    assert body[0]["maneuver_type"] == "ORBIT_RAISE"
    assert body[0]["delta_v_m_s"] == 5.6


def test_get_maneuvers_rejects_bad_confidence() -> None:
    assert client.get("/maneuvers", params={"min_confidence": 2}).status_code == 422


def test_get_baselines(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_baselines(**kwargs):
        return [BASELINE]

    monkeypatch.setattr(mnv_api, "query_baselines", fake_baselines)
    resp = client.get("/maneuvers/baselines")
    assert resp.status_code == 200
    assert resp.json()[0]["type_distribution"] == {"STATION_KEEPING": 6}


def test_maneuver_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/maneuvers" in paths
    assert "/maneuvers/baselines" in paths
