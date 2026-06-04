"""Endpoint authorization: default-deny 401/403 at the API seam (Stage 5).

Deny paths short-circuit before the handler touches the DB, so they run without
infra. The permit paths (which reach the DB) are infra-gated. Tokens are minted
with the app's own secret so the engine validates them exactly as in production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine import db
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.repository import record_alert
from orbital_engine.security.tokens import mint_token

client = TestClient(create_app())


def _token(
    role: str,
    *,
    username: str = "operator1",
    service: str = "JOINT",
    clearance: str = "S",
    scope: tuple[str, ...] = (),
    grants: tuple[str, ...] = (),
) -> str:
    settings = get_settings()
    claims = {
        "sub": username,
        "role": role,
        "service": service,
        "clr": clearance,
        "scope": list(scope),
        "grants": list(grants),
    }
    return mint_token(claims, secret=settings.auth_jwt_secret, ttl_sec=300)


def _auth(role: str, **kw: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role, **kw)}"}  # type: ignore[arg-type]


# --- Default-deny: no session ----------------------------------------------
def test_catalog_requires_auth() -> None:
    assert client.get("/catalog").status_code == 401


def test_conjunctions_requires_auth() -> None:
    assert client.get("/conjunctions").status_code == 401


def test_alerts_requires_auth() -> None:
    assert client.get("/alerts").status_code == 401


def test_ingest_requires_auth() -> None:
    assert client.post("/ingest/run").status_code == 401


# --- Forbidden: authenticated but under-privileged (no DB reached) ----------
def test_viewer_cannot_trigger_ingest() -> None:
    resp = client.post("/ingest/run", headers=_auth("VIEWER"))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden: insufficient_role"


def test_viewer_cannot_acknowledge() -> None:
    resp = client.post("/alerts/x/ack", json={"status": "ACK"}, headers=_auth("VIEWER"))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden: insufficient_role"


def test_analyst_cannot_administer() -> None:
    # ADMINISTER is ADMIN-only even for an analyst.
    assert client.post("/ingest/run", headers=_auth("ANALYST")).status_code == 403


# --- Permit paths (infra-gated) --------------------------------------------
@pytest.fixture
async def infra_up() -> bool:
    if not await db.ping():
        pytest.skip("Postgres not available — skipping authz permit round-trip")
    return True


async def test_viewer_may_query_catalog(infra_up: bool) -> None:
    resp = client.get("/catalog", headers=_auth("VIEWER"))
    assert resp.status_code == 200
    await db.dispose()


async def test_ack_actor_is_the_authenticated_subject(infra_up: bool) -> None:
    # A client cannot forge the actor: the engine stamps the token subject.
    await record_alert(
        {
            "id": "pytest-authz-alert",
            "type": "TEST",
            "severity": None,
            "object_id": None,
            "conjunction_id": None,
            "message": "authz actor test",
            "payload": {},
        }
    )
    resp = client.post(
        "/alerts/pytest-authz-alert/ack",
        json={"status": "ACK", "acknowledged_by": "someone-else"},
        headers=_auth("ANALYST", username="real-analyst"),
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged_by"] == "real-analyst"
    await db.dispose()
