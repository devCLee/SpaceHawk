"""Catalog query/detail/history/state endpoints (deps monkeypatched, no DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine.api import catalog as catalog_api
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.security.tokens import mint_token


def _admin_headers() -> dict[str, str]:
    """A valid ADMIN session so these contract tests reach the handlers (Stage 5)."""
    settings = get_settings()
    token = mint_token(
        {"sub": "operator1", "role": "ADMIN", "service": "JOINT", "clr": "S", "scope": [], "grants": []},
        secret=settings.auth_jwt_secret,
        ttl_sec=300,
    )
    return {"Authorization": f"Bearer {token}"}


# Authenticate every request from this client; authz is exercised in test_authz.
client = TestClient(create_app(), headers=_admin_headers())

ROW = {
    "object_id": "SH:CAT:000025544",
    "norad_cat_id": 25544,
    "object_name": "ISS (ZARYA)",
    "object_type": "PAYLOAD",
    "country_code": "US",
    "tle_line0": "0 ISS (ZARYA)",
    "tle_line1": "1 25544U ...",
    "tle_line2": "2 25544 ...",
}


def test_catalog_passes_filters_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return [ROW]

    monkeypatch.setattr(catalog_api, "query_catalog", fake_query)
    resp = client.get("/catalog", params={"q": "ISS", "object_type": "PAYLOAD", "limit": 10})
    assert resp.status_code == 200
    assert captured == {"q": "ISS", "object_type": "PAYLOAD", "country_code": None, "limit": 10, "offset": 0}
    assert resp.json()[0]["object_name"] == "ISS (ZARYA)"


def test_catalog_rejects_out_of_range_limit() -> None:
    assert client.get("/catalog", params={"limit": 0}).status_code == 422
    assert client.get("/catalog", params={"limit": 99999}).status_code == 422


def test_object_detail_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(object_id: str):
        assert object_id == "SH:CAT:000025544"
        return {"object_id": object_id, "object_name": "ISS (ZARYA)", "norad_cat_id": 25544}

    monkeypatch.setattr(catalog_api, "get_object", fake_get)
    resp = client.get("/catalog/SH:CAT:000025544")
    assert resp.status_code == 200
    assert resp.json()["norad_cat_id"] == 25544


def test_object_detail_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(object_id: str):
        return None

    monkeypatch.setattr(catalog_api, "get_object", fake_get)
    assert client.get("/catalog/SH:CAT:000000000").status_code == 404


def test_object_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_history(object_id: str, limit: int):
        return [{"object_id": object_id, "epoch": "2024-03-10T12:00:00", "mean_motion": 15.5}]

    monkeypatch.setattr(catalog_api, "fetch_history", fake_history)
    resp = client.get("/catalog/SH:CAT:000025544/history", params={"limit": 5})
    assert resp.status_code == 200
    assert resp.json()[0]["mean_motion"] == 15.5


def test_object_state_found_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_state(object_id: str):
        if object_id == "SH:CAT:000025544":
            return {"object_id": object_id, "lat_deg": 1.0, "lon_deg": 2.0, "alt_km": 420.0}
        return None

    monkeypatch.setattr(catalog_api, "read_object_state", fake_state)
    ok = client.get("/catalog/SH:CAT:000025544/state")
    assert ok.status_code == 200 and ok.json()["alt_km"] == 420.0
    assert client.get("/catalog/SH:CAT:000000000/state").status_code == 404


def test_new_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/catalog/{object_id}" in paths
    assert "/catalog/{object_id}/history" in paths
    assert "/catalog/{object_id}/state" in paths
    assert "/state/stream" in paths
