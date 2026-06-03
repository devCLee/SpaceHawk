"""Database access (async SQLAlchemy over psycopg3).

The Orbital Engine is the authoritative owner of the canonical catalog. This
module exposes a lazily-created async engine + session factory and a readiness
ping. The schema itself is managed by Alembic (``migrations/``), not by ORM
metadata, because it relies on PostGIS / TimescaleDB constructs (see migration
0001). We therefore use SQLAlchemy Core against the migrated tables.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from orbital_engine.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def ping() -> bool:
    """True if the database answers ``SELECT 1``; never raises."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness must not propagate
        return False


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
