"""Auth primitives (pure) + the login/me/logout flow (infra-gated)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine import db
from orbital_engine.main import create_app
from orbital_engine.security.attributes import Clearance, Role, Service, Subject
from orbital_engine.security.passwords import hash_password, verify_password
from orbital_engine.security.session import subject_claims, subject_from_claims
from orbital_engine.security.tokens import TokenError, decode_token, mint_token
from orbital_engine.security.users import upsert_user

client = TestClient(create_app())
_SECRET = "unit-test-secret"


# --- Passwords (pure) -------------------------------------------------------
def test_password_roundtrip() -> None:
    h = hash_password("Correct horse battery staple")
    assert verify_password("Correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_verify_rejects_garbage_hash() -> None:
    assert not verify_password("x", "not-a-bcrypt-hash")


# --- Tokens (pure) ----------------------------------------------------------
def test_token_roundtrip() -> None:
    token = mint_token({"sub": "alice"}, secret=_SECRET, ttl_sec=60)
    assert decode_token(token, secret=_SECRET)["sub"] == "alice"


def test_token_rejects_bad_signature() -> None:
    token = mint_token({"sub": "alice"}, secret=_SECRET, ttl_sec=60)
    with pytest.raises(TokenError):
        decode_token(token, secret="other-secret")


def test_token_rejects_expired() -> None:
    token = mint_token({"sub": "alice"}, secret=_SECRET, ttl_sec=-10)
    with pytest.raises(TokenError):
        decode_token(token, secret=_SECRET)


def test_subject_claims_roundtrip() -> None:
    subject = Subject(
        username="bob",
        role=Role.ANALYST,
        service=Service.NAVY,
        clearance=Clearance.SECRET,
        scope=frozenset({"PROTECTED_ASSET"}),
        grants=frozenset({"export"}),
    )
    assert subject_from_claims(subject_claims(subject)) == subject


# --- /auth/me default-deny (no DB needed: 401 precedes any lookup) ----------
def test_me_requires_session() -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_bad_bearer() -> None:
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401


def test_logout_is_idempotent() -> None:
    assert client.post("/auth/logout").status_code == 200


# --- Full flow (infra-gated) ------------------------------------------------
@pytest.fixture
async def infra_up() -> bool:
    if not await db.ping():
        pytest.skip("Postgres not available — skipping auth flow round-trip")
    return True


async def test_login_me_logout_flow(infra_up: bool) -> None:
    await upsert_user(
        username="pytest.analyst",
        password_hash=hash_password("s3cret-pw"),
        role="ANALYST",
        service="JOINT",
        clearance="S",
        scope=["PROTECTED_ASSET"],
        grants=["export"],
        is_approved=True,
    )
    with TestClient(create_app()) as flow:
        bad = flow.post("/auth/login", json={"username": "pytest.analyst", "password": "nope"})
        assert bad.status_code == 401

        ok = flow.post("/auth/login", json={"username": "pytest.analyst", "password": "s3cret-pw"})
        assert ok.status_code == 200
        body = ok.json()
        assert body["role"] == "ANALYST"
        assert body["grants"] == ["export"]

        me = flow.get("/auth/me")  # cookie carried by the client jar
        assert me.status_code == 200
        assert me.json()["username"] == "pytest.analyst"

        flow.post("/auth/logout")
        assert flow.get("/auth/me").status_code == 401

    await db.dispose()


async def test_unapproved_user_cannot_login(infra_up: bool) -> None:
    await upsert_user(
        username="pytest.pending",
        password_hash=hash_password("pw"),
        role="VIEWER",
        service="ARMY",
        is_approved=False,
    )
    resp = client.post("/auth/login", json={"username": "pytest.pending", "password": "pw"})
    assert resp.status_code == 401
    await db.dispose()
