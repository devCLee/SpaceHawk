"""Per-user watchlist persistence (SQLAlchemy Core over the migrated schema).

A user's 관심 목록 lives server-side as ``watchlist_item`` rows (one per
``(username, object_id)``; ``object_id`` is the catalog USOID the catalog/web use
everywhere). This module declares the Core :class:`~sqlalchemy.Table` handle (the
authoritative DDL lives in migration ``0012_watchlist``) and the three async
repository functions the API and the report assembler call:

* :func:`list_watchlist` — the user's object ids (newest first).
* :func:`add_watchlist` — idempotent add (``ON CONFLICT DO NOTHING``).
* :func:`remove_watchlist` — remove (a missing row is a no-op).

The connection is *injected* (the caller owns its lifecycle), mirroring
``assemble_daily`` / ``create_report_job``: the API router opens its own
``get_engine().begin()`` / ``.connect()`` and passes it in.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    text,
)


class _Conn(Protocol):
    """The injected read/write connection: just what these helpers call on it."""

    async def execute(self, statement: Any, parameters: Any = ...) -> Any: ...


# Standalone metadata: a code-side handle for query building only. The
# authoritative DDL (table + unique constraint + index) lives in migration 0012.
metadata = MetaData()

watchlist_item = Table(
    "watchlist_item",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("username", String, nullable=False, index=True),
    Column("object_id", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


async def list_watchlist(conn: _Conn, username: str) -> list[str]:
    """Return one user's watchlisted ``object_id``s, most-recently-added first."""
    result = await conn.execute(
        text(
            "SELECT object_id FROM watchlist_item "
            "WHERE username = :u ORDER BY created_at DESC, id DESC"
        ),
        {"u": username},
    )
    return [row["object_id"] for row in result.mappings()]


async def add_watchlist(conn: _Conn, username: str, object_id: str) -> None:
    """Add ``object_id`` to ``username``'s watchlist (idempotent).

    A duplicate (the user already watches this object) is a no-op via the
    UNIQUE(username, object_id) constraint — no error, no duplicate row.
    """
    await conn.execute(
        text(
            "INSERT INTO watchlist_item (username, object_id) VALUES (:u, :oid) "
            "ON CONFLICT (username, object_id) DO NOTHING"
        ),
        {"u": username, "oid": object_id},
    )


async def remove_watchlist(conn: _Conn, username: str, object_id: str) -> None:
    """Remove ``object_id`` from ``username``'s watchlist (missing row is a no-op)."""
    await conn.execute(
        text("DELETE FROM watchlist_item WHERE username = :u AND object_id = :oid"),
        {"u": username, "oid": object_id},
    )


__all__ = [
    "add_watchlist",
    "list_watchlist",
    "remove_watchlist",
    "watchlist_item",
]
