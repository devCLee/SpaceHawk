"""Per-user watchlist: repository semantics + the ABAC-gated HTTP surface (A1).

Two layers, mirroring the engine's test conventions:

* Repository (``list_watchlist`` / ``add_watchlist`` / ``remove_watchlist``) is
  exercised against REAL Postgres — idempotent add, list ordering, remove-missing
  no-op, and per-user isolation — and is skipped when infra is down (the
  ``test_gp_history`` / ``test_assembler`` ``infra_up`` skip pattern).
* The HTTP routes: the auth deny paths (401 unauth) short-circuit before any DB
  work, so they run WITHOUT infra (mirrors ``test_authz`` / ``test_reports_api``);
  the permit paths (VIEWER allowed; one user can't see another's) are infra-gated.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbital_engine import db
from orbital_engine.config import get_settings
from orbital_engine.main import create_app
from orbital_engine.security.tokens import mint_token
from orbital_engine.watchlist import add_watchlist, list_watchlist, remove_watchlist

client = TestClient(create_app())


def _token(role: str, *, username: str) -> str:
    settings = get_settings()
    claims = {
        "sub": username,
        "role": role,
        "service": "JOINT",
        "clr": "S",
        "scope": [],
        "grants": [],
    }
    return mint_token(claims, secret=settings.auth_jwt_secret, ttl_sec=300)


def _auth(role: str, *, username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role, username=username)}"}


# --------------------------------------------------------------------------- #
# Auth deny paths (no infra reached)
# --------------------------------------------------------------------------- #


def test_get_watchlist_requires_auth() -> None:
    assert client.get("/watchlist").status_code == 401


def test_add_watchlist_requires_auth() -> None:
    assert client.post("/watchlist", json={"object_id": "SH:CAT:1"}).status_code == 401


def test_delete_watchlist_requires_auth() -> None:
    assert client.delete("/watchlist/SH:CAT:1").status_code == 401


def test_watchlist_paths_in_openapi() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/watchlist" in paths
    assert "/watchlist/{object_id}" in paths


# --------------------------------------------------------------------------- #
# Repository semantics (infra-gated)
# --------------------------------------------------------------------------- #


@pytest.fixture
async def infra_up() -> bool:
    if not await db.ping():
        pytest.skip("Postgres not available — skipping watchlist round-trip")
    return True


async def _clear(username: str) -> None:
    from sqlalchemy import text

    async with db.get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM watchlist_item WHERE username = :u"), {"u": username})


async def test_repo_add_list_remove_roundtrip(infra_up: bool) -> None:
    user = "pytest-wl-user-1"
    await _clear(user)
    try:
        async with db.get_engine().begin() as conn:
            await add_watchlist(conn, user, "SH:CAT:000000001")
            await add_watchlist(conn, user, "SH:CAT:000000002")
        async with db.get_engine().connect() as conn:
            ids = await list_watchlist(conn, user)
        assert set(ids) == {"SH:CAT:000000001", "SH:CAT:000000002"}

        async with db.get_engine().begin() as conn:
            await remove_watchlist(conn, user, "SH:CAT:000000001")
        async with db.get_engine().connect() as conn:
            ids = await list_watchlist(conn, user)
        assert ids == ["SH:CAT:000000002"]
    finally:
        await _clear(user)
        await db.dispose()


async def test_repo_add_is_idempotent(infra_up: bool) -> None:
    user = "pytest-wl-user-2"
    await _clear(user)
    try:
        async with db.get_engine().begin() as conn:
            await add_watchlist(conn, user, "SH:CAT:000000003")
            await add_watchlist(conn, user, "SH:CAT:000000003")  # duplicate → no-op
        async with db.get_engine().connect() as conn:
            ids = await list_watchlist(conn, user)
        assert ids == ["SH:CAT:000000003"]  # one row, not two
    finally:
        await _clear(user)
        await db.dispose()


async def test_repo_remove_missing_is_noop(infra_up: bool) -> None:
    user = "pytest-wl-user-3"
    await _clear(user)
    try:
        async with db.get_engine().begin() as conn:
            await remove_watchlist(conn, user, "SH:CAT:does-not-exist")  # no error
        async with db.get_engine().connect() as conn:
            ids = await list_watchlist(conn, user)
        assert ids == []
    finally:
        await _clear(user)
        await db.dispose()


async def test_repo_isolation_between_users(infra_up: bool) -> None:
    a, b = "pytest-wl-user-a", "pytest-wl-user-b"
    await _clear(a)
    await _clear(b)
    try:
        async with db.get_engine().begin() as conn:
            await add_watchlist(conn, a, "SH:CAT:000000010")
            await add_watchlist(conn, b, "SH:CAT:000000020")
        async with db.get_engine().connect() as conn:
            ids_a = await list_watchlist(conn, a)
            ids_b = await list_watchlist(conn, b)
        assert ids_a == ["SH:CAT:000000010"]
        assert ids_b == ["SH:CAT:000000020"]  # a never sees b's, and vice versa
    finally:
        await _clear(a)
        await _clear(b)
        await db.dispose()


# --------------------------------------------------------------------------- #
# HTTP permit paths (infra-gated): VIEWER allowed; per-user isolation
# --------------------------------------------------------------------------- #


async def test_viewer_can_manage_own_watchlist(infra_up: bool) -> None:
    user = "pytest-wl-http-viewer"
    await _clear(user)
    try:
        # VIEWER (the role floor) may add to and read their own list.
        add = client.post(
            "/watchlist", json={"object_id": "SH:CAT:000000099"}, headers=_auth("VIEWER", username=user)
        )
        assert add.status_code == 201
        assert add.json()["object_ids"] == ["SH:CAT:000000099"]

        got = client.get("/watchlist", headers=_auth("VIEWER", username=user))
        assert got.status_code == 200
        assert got.json()["object_ids"] == ["SH:CAT:000000099"]

        # DELETE removes it; the list is then empty.
        rm = client.delete("/watchlist/SH:CAT:000000099", headers=_auth("VIEWER", username=user))
        assert rm.status_code == 200
        assert rm.json()["object_ids"] == []
    finally:
        await _clear(user)
        await db.dispose()


async def test_http_one_user_cannot_see_anothers(infra_up: bool) -> None:
    a, b = "pytest-wl-http-a", "pytest-wl-http-b"
    await _clear(a)
    await _clear(b)
    try:
        client.post(
            "/watchlist", json={"object_id": "SH:CAT:000000111"}, headers=_auth("ANALYST", username=a)
        )
        # b's view is scoped to b — it never includes a's object.
        got_b = client.get("/watchlist", headers=_auth("VIEWER", username=b))
        assert got_b.status_code == 200
        assert got_b.json()["object_ids"] == []
    finally:
        await _clear(a)
        await _clear(b)
        await db.dispose()
