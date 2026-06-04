"""Seed a small tri-service operator set for development / pilot onboarding.

Run with ``python -m orbital_engine.security.seed`` after migrations. Every user
gets the same dev password (``ORBITAL_ENGINE_SEED_PASSWORD``, default ``changeme``)
— this is a development convenience, never a production provisioning path. The set
exercises each role, each service, and the clearance / need-to-know / export
attributes the PDP gates on.
"""

from __future__ import annotations

import asyncio

from orbital_engine.config import get_settings
from orbital_engine.db import dispose
from orbital_engine.security.passwords import hash_password
from orbital_engine.security.users import upsert_user

# (username, role, service, clearance, scope, grants)
_SEED_USERS: list[tuple[str, str, str, str, list[str], list[str]]] = [
    ("af.viewer", "VIEWER", "AIR_FORCE", "U", [], []),
    ("army.viewer", "VIEWER", "ARMY", "U", [], []),
    ("navy.viewer", "VIEWER", "NAVY", "U", [], []),
    ("af.analyst", "ANALYST", "AIR_FORCE", "S", ["PROTECTED_ASSET"], ["export"]),
    ("joint.analyst", "ANALYST", "JOINT", "S", ["PROTECTED_ASSET"], ["export"]),
    ("admin", "ADMIN", "JOINT", "S", ["PROTECTED_ASSET"], ["export"]),
]


async def seed() -> int:
    """Upsert the demo users; returns how many were written."""
    password_hash = hash_password(get_settings().seed_password)
    for username, role, service, clearance, scope, grants in _SEED_USERS:
        await upsert_user(
            username=username,
            password_hash=password_hash,
            role=role,
            service=service,
            clearance=clearance,
            scope=scope,
            grants=grants,
            is_approved=True,
        )
    await dispose()
    return len(_SEED_USERS)


def main() -> None:
    count = asyncio.run(seed())
    print(f"seeded {count} users")  # noqa: T201 - CLI feedback


if __name__ == "__main__":
    main()
