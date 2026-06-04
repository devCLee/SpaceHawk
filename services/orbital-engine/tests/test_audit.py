"""Audit log: ADMIN-only access (pure) + write/query/immutability (infra-gated)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from orbital_engine import db
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.security.tokens import mint_token

client = TestClient(create_app())


def _auth(role: str, *, username: str = "operator1") -> dict[str, str]:
    settings = get_settings()
    token = mint_token(
        {"sub": username, "role": role, "service": "JOINT", "clr": "S", "scope": [], "grants": []},
        secret=settings.auth_jwt_secret,
        ttl_sec=300,
    )
    return {"Authorization": f"Bearer {token}"}


# --- Access control on the audit view (no DB reached) -----------------------
def test_audit_requires_auth() -> None:
    assert client.get("/audit").status_code == 401


def test_audit_forbidden_for_analyst() -> None:
    resp = client.get("/audit", headers=_auth("ANALYST"))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden: insufficient_role"


# --- Write / query / immutability (infra-gated) -----------------------------
@pytest.fixture
async def infra_up() -> bool:
    if not await db.ping():
        pytest.skip("Postgres not available — skipping audit round-trip")
    return True


async def test_denied_access_is_audited(infra_up: bool) -> None:
    # A viewer's blocked ingest attempt must leave a deny row.
    assert client.post("/ingest/run", headers=_auth("VIEWER", username="sneaky")).status_code == 403

    resp = client.get("/audit", params={"decision": "deny", "limit": 50}, headers=_auth("ADMIN"))
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["subject"] == "sneaky" and r["action"] == "ADMINISTER" for r in rows)
    await db.dispose()


async def test_audit_log_is_append_only(infra_up: bool) -> None:
    # The DB trigger must reject any UPDATE/DELETE on audit_log.
    with pytest.raises(Exception):  # noqa: B017,PT011 - DB raises a driver error
        async with db.get_engine().begin() as conn:
            await conn.execute(text("UPDATE audit_log SET reason = 'tampered'"))
    await db.dispose()
