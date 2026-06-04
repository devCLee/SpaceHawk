"""Persistence for ``app_user`` — the credential + attribute store.

A user row carries exactly the ABAC subject attributes (role, service, clearance,
need-to-know ``scope``, capability ``grants``) plus a bcrypt password hash and an
approval flag. SQLAlchemy Core over the Alembic-managed table, matching the
catalog ``repository`` convention.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from orbital_engine.db import get_engine

_USER_COLUMNS = (
    "username, password_hash, role, service, clearance, scope, grants, "
    "is_approved, created_at, last_login"
)


async def get_user(username: str) -> dict[str, Any] | None:
    """Return one user's row (including the password hash), or None."""
    sql = text(f"SELECT {_USER_COLUMNS} FROM app_user WHERE username = :u")
    async with get_engine().connect() as conn:
        row = (await conn.execute(sql, {"u": username})).mappings().first()
        return dict(row) if row else None


async def update_last_login(username: str) -> None:
    """Stamp a successful login (best-effort audit trail of access)."""
    sql = text("UPDATE app_user SET last_login = now() WHERE username = :u")
    async with get_engine().begin() as conn:
        await conn.execute(sql, {"u": username})


_UPSERT_SQL = text(
    """
    INSERT INTO app_user
        (username, password_hash, role, service, clearance, scope, grants, is_approved)
    VALUES
        (:username, :password_hash, :role, :service, :clearance, :scope, :grants, :is_approved)
    ON CONFLICT (username) DO UPDATE SET
        password_hash = EXCLUDED.password_hash,
        role          = EXCLUDED.role,
        service       = EXCLUDED.service,
        clearance     = EXCLUDED.clearance,
        scope         = EXCLUDED.scope,
        grants        = EXCLUDED.grants,
        is_approved   = EXCLUDED.is_approved
    """
)


async def upsert_user(
    *,
    username: str,
    password_hash: str,
    role: str,
    service: str,
    clearance: str = "U",
    scope: list[str] | None = None,
    grants: list[str] | None = None,
    is_approved: bool = True,
) -> None:
    """Create or replace a user (used by the seed script)."""
    async with get_engine().begin() as conn:
        await conn.execute(
            _UPSERT_SQL,
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "service": service,
                "clearance": clearance,
                "scope": list(scope or []),
                "grants": list(grants or []),
                "is_approved": is_approved,
            },
        )
