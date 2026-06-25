"""Per-user watchlist (관심 목록) endpoints (HWPX pipeline A1).

A user's watchlist is persisted server-side and is strictly personal: every route
is scoped to the authenticated ``subject.username`` (see
:mod:`orbital_engine.watchlist`), so a caller can only read or mutate their OWN
list — one user can never see or change another's. The list stores the catalog
``object_id`` (the USOID used everywhere in the catalog/web), so the daily report
can intersect it directly against ``space_object.object_id``.

ABAC: the ``WATCHLIST`` data domain is floored at ``VIEWER`` for both READ and the
write action (``ACKNOWLEDGE`` reused as the mutate verb) — a personal preference
list is not classified data, so any authenticated user manages their own. An
anonymous caller is a 401; an authenticated one is always permitted on their own
rows. Handlers open their own async connection from the shared engine (the
repository convention; no FastAPI DB Depends): writes under ``begin()``, the read
under ``connect()``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from orbital_engine.db import get_engine
from orbital_engine.security.attributes import Action, DataDomain, Subject
from orbital_engine.security.enforce import requires
from orbital_engine.watchlist import add_watchlist, list_watchlist, remove_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistResponse(BaseModel):
    """The current user's watchlisted catalog object ids."""

    object_ids: list[str]


class AddWatchlistRequest(BaseModel):
    """Body for adding one object to the current user's watchlist."""

    object_id: str


@router.get("", response_model=WatchlistResponse, summary="The current user's watchlist")
async def get_watchlist(
    subject: Subject = Depends(requires(DataDomain.WATCHLIST, Action.READ)),
) -> WatchlistResponse:
    async with get_engine().connect() as conn:
        object_ids = await list_watchlist(conn, subject.username)
    return WatchlistResponse(object_ids=object_ids)


@router.post(
    "",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an object to the current user's watchlist (idempotent)",
)
async def add_to_watchlist(
    body: AddWatchlistRequest,
    subject: Subject = Depends(requires(DataDomain.WATCHLIST, Action.ACKNOWLEDGE)),
) -> WatchlistResponse:
    async with get_engine().begin() as conn:
        await add_watchlist(conn, subject.username, body.object_id)
        object_ids = await list_watchlist(conn, subject.username)
    return WatchlistResponse(object_ids=object_ids)


@router.delete(
    "/{object_id}",
    response_model=WatchlistResponse,
    summary="Remove an object from the current user's watchlist (no-op if absent)",
)
async def remove_from_watchlist(
    object_id: str,
    subject: Subject = Depends(requires(DataDomain.WATCHLIST, Action.ACKNOWLEDGE)),
) -> WatchlistResponse:
    async with get_engine().begin() as conn:
        await remove_watchlist(conn, subject.username, object_id)
        object_ids = await list_watchlist(conn, subject.username)
    return WatchlistResponse(object_ids=object_ids)
