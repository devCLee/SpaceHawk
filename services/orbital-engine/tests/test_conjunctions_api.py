"""Conjunction + alert-log endpoints (repo monkeypatched, no DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine.api import conjunctions as conj_api
from orbital_engine.main import create_app

client = TestClient(create_app())

CONJ = {
    "id": "CDM:1",
    "source": "CDM",
    "cdm_id": "1",
    "primary_object_id": "SH:CAT:000025544",
    "primary_norad_cat_id": 25544,
    "primary_name": "ISS (ZARYA)",
    "secondary_object_id": "SH:CAT:000033333",
    "secondary_norad_cat_id": 33333,
    "secondary_name": "COSMOS DEBRIS",
    "tca": "2026-06-05T12:00:00",
    "miss_distance_km": 0.45,
    "relative_speed_km_s": 11.2,
    "probability": 3e-4,
    "severity": "HIGH",
    "screened_at": "2026-06-04T00:00:00",
}

ALERT = {
    "id": "CDM:1",
    "type": "conjunction",
    "severity": "HIGH",
    "object_id": "SH:CAT:000025544",
    "conjunction_id": "CDM:1",
    "message": "ISS (ZARYA) ↔ COSMOS DEBRIS: 0.45 km",
    "payload": {"id": "CDM:1"},
    "status": "NEW",
    "acknowledged_by": None,
    "acknowledged_at": None,
    "created_at": "2026-06-04T00:00:00",
    "updated_at": "2026-06-04T00:00:00",
}


def test_get_conjunctions_passes_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return [CONJ]

    monkeypatch.setattr(conj_api, "query_conjunctions", fake_query)
    resp = client.get("/conjunctions", params={"severity": "HIGH", "limit": 50})
    assert resp.status_code == 200
    assert captured == {"severity": "HIGH", "min_probability": None, "limit": 50}
    body = resp.json()
    assert body[0]["primary_name"] == "ISS (ZARYA)"
    assert body[0]["severity"] == "HIGH"


def test_get_conjunctions_rejects_bad_probability() -> None:
    assert client.get("/conjunctions", params={"min_probability": 2}).status_code == 422


def test_get_alerts_filters_by_status(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_alerts(**kwargs):
        captured.update(kwargs)
        return [ALERT]

    monkeypatch.setattr(conj_api, "query_alerts", fake_alerts)
    resp = client.get("/alerts", params={"status": "NEW"})
    assert resp.status_code == 200
    assert captured == {"status": "NEW", "limit": 100}
    assert resp.json()[0]["conjunction_id"] == "CDM:1"


def test_acknowledge_alert_found(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_set(alert_id: str, *, status: str, acknowledged_by):
        captured.update({"id": alert_id, "status": status, "by": acknowledged_by})
        return {**ALERT, "status": status, "acknowledged_by": acknowledged_by}

    monkeypatch.setattr(conj_api, "set_alert_status", fake_set)
    resp = client.post(
        "/alerts/CDM:1/ack", json={"status": "ACK", "acknowledged_by": "analyst1"}
    )
    assert resp.status_code == 200
    assert captured == {"id": "CDM:1", "status": "ACK", "by": "analyst1"}
    assert resp.json()["status"] == "ACK"


def test_acknowledge_alert_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_set(alert_id: str, *, status: str, acknowledged_by):
        return None

    monkeypatch.setattr(conj_api, "set_alert_status", fake_set)
    assert client.post("/alerts/nope/ack", json={}).status_code == 404


def test_conjunction_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/conjunctions" in paths
    assert "/alerts" in paths
    assert "/alerts/{alert_id}/ack" in paths
