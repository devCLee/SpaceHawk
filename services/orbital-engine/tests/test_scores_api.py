"""Composite threat-score endpoint (repo monkeypatched, no DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine.api import scores as scores_api
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.security.tokens import mint_token


def _headers(role: str) -> dict[str, str]:
    settings = get_settings()
    token = mint_token(
        {"sub": "operator1", "role": role, "service": "JOINT", "clr": "S", "scope": [], "grants": []},
        secret=settings.auth_jwt_secret,
        ttl_sec=300,
    )
    return {"Authorization": f"Bearer {token}"}


client = TestClient(create_app(), headers=_headers("ADMIN"))

MANEUVER_ROW = {
    "object_id": "SH:CAT:000000200",
    "object_name": "THREAT SAT",
    "max_confidence": 0.9,
    "max_delta_v_m_s": 5.6,
    "event_count": 2,
}

CONJUNCTION_ROW = {
    "object_id": "SH:CAT:000000200",
    "object_name": "THREAT SAT (CONJ)",
    "max_pc": 1e-4,
    "severity": "HIGH",
    "min_miss_km": 0.8,
    "event_count": 3,
}

RPO_ROW = {
    "object_id": "SH:CAT:000000300",
    "object_name": "SHADOWER",
    "max_coplanarity": 0.6,
    "event_count": 1,
}

ANOMALY_ROW = {
    "object_id": "SH:CAT:000000200",
    "object_name": "THREAT SAT (ANOM)",
    "max_sigma": 3.0,
    "novel_type": False,
    "event_count": 1,
}

# 800 km circular LARGE fragment -> risk_score ~93 (Critical, above standalone floor).
DEBRIS_HOT = {
    "object_id": "SH:CAT:000000400",
    "object_name": "HOT DEBRIS",
    "rcs_size": "LARGE",
    "apoapsis_km": 800.0,
    "periapsis_km": 800.0,
}

# 400 km SMALL fragment -> risk_score ~5 (debris-only, below floor, excluded).
DEBRIS_COLD = {
    "object_id": "SH:CAT:000000500",
    "object_name": "COLD DEBRIS",
    "rcs_size": "SMALL",
    "apoapsis_km": 400.0,
    "periapsis_km": 400.0,
}


def _patch_all(
    monkeypatch: pytest.MonkeyPatch,
    *,
    maneuvers=(MANEUVER_ROW,),
    conjunctions=(CONJUNCTION_ROW,),
    rpos=(RPO_ROW,),
    anomalies=(ANOMALY_ROW,),
    debris=(DEBRIS_HOT, DEBRIS_COLD),
    captured: dict | None = None,
) -> None:
    def fake(rows):
        async def _q(**kwargs):
            if captured is not None:
                captured.update(kwargs)
            return list(rows)

        return _q

    monkeypatch.setattr(scores_api, "score_maneuver_aggregates", fake(maneuvers))
    monkeypatch.setattr(scores_api, "score_conjunction_aggregates", fake(conjunctions))
    monkeypatch.setattr(scores_api, "score_rpo_aggregates", fake(rpos))
    monkeypatch.setattr(scores_api, "score_anomaly_aggregates", fake(anomalies))
    monkeypatch.setattr(scores_api, "query_debris", fake(debris))


def test_scores_shape_and_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_all(monkeypatch)
    resp = client.get("/scores")
    assert resp.status_code == 200
    body = resp.json()

    assert body["window_days"] == 30
    assert body["weights"]["conjunction"] == 0.30
    assert body["generated_at"]

    ids = [i["object_id"] for i in body["items"]]
    # Cold debris-only object is below the standalone floor -> excluded.
    assert "SH:CAT:000000500" not in ids
    assert set(ids) == {"SH:CAT:000000200", "SH:CAT:000000300", "SH:CAT:000000400"}
    # Sorted by composite, descending.
    composites = [i["composite"] for i in body["items"]]
    assert composites == sorted(composites, reverse=True)

    multi = next(i for i in body["items"] if i["object_id"] == "SH:CAT:000000200")
    # Name precedence: the maneuver rollup's name wins over conjunction/anomaly.
    assert multi["object_name"] == "THREAT SAT"
    # maneuver 0.9, conjunction log10(1e-4)=0.75, anomaly sigma 3/6=0.5, no rpo/debris.
    assert multi["components"]["maneuver"] == 0.9
    assert multi["components"]["conjunction"] == 0.75
    assert multi["components"]["anomaly"] == 0.5
    assert multi["components"]["rpo"] is None
    assert multi["components"]["debris"] is None
    expected = round(100 * (0.25 * 0.9 + 0.30 * 0.75 + 0.15 * 0.5) / (0.25 + 0.30 + 0.15), 1)
    assert multi["composite"] == expected
    assert multi["raw"]["min_miss_km"] == 0.8
    assert multi["raw"]["maneuver_count"] == 2

    # Single-signal RPO object reweights to 100 * coplanarity.
    rpo = next(i for i in body["items"] if i["object_id"] == "SH:CAT:000000300")
    assert rpo["composite"] == 60.0
    assert rpo["level"] == "High"

    summary = body["summary"]
    assert summary["total"] == 3
    assert summary["by_method"] == {
        "conjunction": 1,
        "maneuver": 1,
        "rpo": 1,
        "anomaly": 1,
        "debris": 1,
    }
    assert sum(summary["by_level"].values()) == 3


def test_scores_forwards_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    _patch_all(monkeypatch, captured=captured)
    assert client.get("/scores", params={"window_days": 7}).status_code == 200
    assert captured["window_days"] == 7


def test_scores_rejects_bad_params() -> None:
    assert client.get("/scores", params={"window_days": 0}).status_code == 422
    assert client.get("/scores", params={"limit": 0}).status_code == 422


def test_scores_viewer_forbidden() -> None:
    resp = client.get("/scores", headers=_headers("VIEWER"))
    assert resp.status_code == 403


def test_scores_history_shape_and_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    anchors: list = []

    def fake(rows):
        async def _q(**kwargs):
            if "as_of" in kwargs:
                anchors.append(kwargs["as_of"])
            return list(rows)

        return _q

    monkeypatch.setattr(scores_api, "score_maneuver_aggregates", fake([MANEUVER_ROW]))
    monkeypatch.setattr(scores_api, "score_conjunction_aggregates", fake([]))
    monkeypatch.setattr(scores_api, "score_rpo_aggregates", fake([]))
    monkeypatch.setattr(scores_api, "score_anomaly_aggregates", fake([]))
    monkeypatch.setattr(scores_api, "query_debris", fake([DEBRIS_HOT]))

    resp = client.get("/scores/history", params={"days": 5})
    assert resp.status_code == 200
    body = resp.json()

    assert body["days"] == 5
    assert len(body["points"]) == 5
    # Dates ascend and every point carries the full level histogram.
    dates = [p["date"] for p in body["points"]]
    assert dates == sorted(dates)
    assert set(body["points"][0]["by_level"]) == {"Critical", "High", "Medium", "Low"}
    # Maneuver-only object (100) and hot debris (~93) are both Critical, daily.
    assert all(p["by_level"]["Critical"] == 2 for p in body["points"])
    # Each of the 5 days anchored the maneuver aggregate at a distinct as_of.
    maneuver_anchors = [a for a in anchors if a is not None]
    assert len(set(maneuver_anchors)) >= 5


def test_scores_history_rejects_bad_days() -> None:
    assert client.get("/scores/history", params={"days": 1}).status_code == 422


def test_scores_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/scores" in paths
    assert "/scores/history" in paths
