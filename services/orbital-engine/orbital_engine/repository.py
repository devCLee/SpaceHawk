"""Catalog persistence (SQLAlchemy Core over the Alembic-managed schema).

Writes go through an idempotent upsert keyed on the USOID (``object_id``) so a
re-ingest of the same group refreshes rows in place. Reads return plain dicts —
the propagation loop and the BFF only need a projection, not ORM entities.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from orbital_engine.db import get_engine
from orbital_engine.domain.space_object import SpaceObject

# Columns written on ingest. ``ingested_at`` is omitted so the DB default (now())
# stamps every upsert; ``object_id`` is the conflict target (never updated).
_COLUMNS: tuple[str, ...] = (
    "object_id",
    "norad_cat_id",
    "intl_designator",
    "gp_id",
    "source_file_id",
    "data_source",
    "originator",
    "ccsds_omm_vers",
    "comment",
    "creation_date",
    "object_name",
    "object_type",
    "rcs_size",
    "classification_type",
    "country_code",
    "launch_date",
    "decay_date",
    "site",
    "center_name",
    "ref_frame",
    "time_system",
    "mean_element_theory",
    "epoch",
    "mean_motion",
    "eccentricity",
    "inclination",
    "ra_of_asc_node",
    "arg_of_pericenter",
    "mean_anomaly",
    "ephemeris_type",
    "element_set_no",
    "rev_at_epoch",
    "bstar",
    "mean_motion_dot",
    "mean_motion_ddot",
    "semimajor_axis_km",
    "period_min",
    "apoapsis_km",
    "periapsis_km",
    "tle_line0",
    "tle_line1",
    "tle_line2",
)

_UPDATE_COLS = tuple(c for c in _COLUMNS if c != "object_id")

_UPSERT_SQL = text(
    "INSERT INTO space_object ({cols}) VALUES ({binds}) "
    "ON CONFLICT (object_id) DO UPDATE SET {updates}, ingested_at = now()".format(
        cols=", ".join(_COLUMNS),
        binds=", ".join(f":{c}" for c in _COLUMNS),
        updates=", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATE_COLS),
    )
)


def _to_row(obj: SpaceObject) -> dict[str, Any]:
    data = obj.model_dump(mode="python")
    return {c: data.get(c) for c in _COLUMNS}


async def upsert_objects(objects: list[SpaceObject]) -> int:
    """Upsert a batch of canonical records. Returns the number written."""
    if not objects:
        return 0
    rows = [_to_row(o) for o in objects]
    async with get_engine().begin() as conn:
        await conn.execute(_UPSERT_SQL, rows)
    return len(rows)


async def fetch_catalog(limit: int | None = None) -> list[dict[str, Any]]:
    """Return current (non-decayed) catalog rows for propagation/display."""
    sql = (
        "SELECT object_id, norad_cat_id, object_name, object_type, country_code, "
        "       epoch, mean_motion, inclination, eccentricity, "
        "       tle_line0, tle_line1, tle_line2 "
        "FROM space_object WHERE decay_date IS NULL ORDER BY object_name"
    )
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    async with get_engine().connect() as conn:
        result = await conn.execute(text(sql))
        return [dict(row) for row in result.mappings()]


async def count_objects() -> int:
    async with get_engine().connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM space_object"))
        return int(result.scalar_one())


# Columns returned to the catalog list/feed (matches the API CatalogObject).
_LIST_COLUMNS = (
    "object_id, norad_cat_id, object_name, object_type, country_code, "
    "tle_line0, tle_line1, tle_line2"
)


async def query_catalog(
    *,
    q: str | None = None,
    object_type: str | None = None,
    country_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Filter the on-orbit catalog. All filters are optional and AND-combined.

    ``q`` matches object name, international designator, or NORAD id substring.
    Values are bound parameters (no string interpolation); enum/int columns are
    compared as text so a plain string param needs no cast.
    """
    clauses = ["decay_date IS NULL"]
    params: dict[str, Any] = {}
    if q:
        clauses.append(
            "(object_name ILIKE :q OR intl_designator ILIKE :q "
            "OR CAST(norad_cat_id AS text) LIKE :q)"
        )
        params["q"] = f"%{q}%"
    if object_type:
        clauses.append("object_type::text = :otype")
        params["otype"] = object_type
    if country_code:
        clauses.append("country_code = :cc")
        params["cc"] = country_code
    where = " AND ".join(clauses)
    sql = (
        f"SELECT {_LIST_COLUMNS} FROM space_object WHERE {where} "
        "ORDER BY object_name LIMIT :lim OFFSET :off"
    )
    params["lim"] = max(1, min(int(limit), 5000))
    params["off"] = max(0, int(offset))
    async with get_engine().connect() as conn:
        result = await conn.execute(text(sql), params)
        return [dict(row) for row in result.mappings()]


# Full record returned by the object-detail endpoint.
_DETAIL_COLUMNS = (
    "object_id, norad_cat_id, intl_designator, data_source, originator, "
    "object_name, object_type, rcs_size, classification_type, country_code, "
    "launch_date, decay_date, site, epoch, mean_motion, eccentricity, inclination, "
    "ra_of_asc_node, arg_of_pericenter, mean_anomaly, ephemeris_type, bstar, "
    "mean_motion_dot, mean_motion_ddot, semimajor_axis_km, period_min, "
    "apoapsis_km, periapsis_km, mean_element_theory, ref_frame, "
    "tle_line0, tle_line1, tle_line2, ingested_at"
)


async def get_object(object_id: str) -> dict[str, Any] | None:
    """Return one object's full record, or None if not catalogued."""
    sql = f"SELECT {_DETAIL_COLUMNS} FROM space_object WHERE object_id = :oid"
    async with get_engine().connect() as conn:
        result = await conn.execute(text(sql), {"oid": object_id})
        row = result.mappings().first()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# gp_history — append-only element-set time series (TimescaleDB hypertable).
# One row per (object, epoch); the substrate for maneuver/RPO history (P2a).
# Re-ingesting the same element set is a no-op (PK conflict ignored).
# ---------------------------------------------------------------------------
_HISTORY_COLUMNS: tuple[str, ...] = (
    "object_id",
    "epoch",
    "data_source",
    "gp_id",
    "mean_motion",
    "eccentricity",
    "inclination",
    "ra_of_asc_node",
    "arg_of_pericenter",
    "mean_anomaly",
    "bstar",
    "semimajor_axis_km",
    "period_min",
    "apoapsis_km",
    "periapsis_km",
    "tle_line1",
    "tle_line2",
)

_HISTORY_INSERT_SQL = text(
    "INSERT INTO gp_history ({cols}) VALUES ({binds}) "
    "ON CONFLICT (object_id, epoch) DO NOTHING".format(
        cols=", ".join(_HISTORY_COLUMNS),
        binds=", ".join(f":{c}" for c in _HISTORY_COLUMNS),
    )
)


def _to_history_row(obj: SpaceObject) -> dict[str, Any]:
    data = obj.model_dump(mode="python")
    return {c: data.get(c) for c in _HISTORY_COLUMNS}


async def append_history(objects: list[SpaceObject]) -> int:
    """Append each object's current element set to gp_history (idempotent per epoch).

    Returns the number of rows offered; a row already present for (object, epoch)
    is silently skipped so re-ingests don't duplicate history.
    """
    if not objects:
        return 0
    rows = [_to_history_row(o) for o in objects]
    async with get_engine().begin() as conn:
        await conn.execute(_HISTORY_INSERT_SQL, rows)
    return len(rows)


async def fetch_history(object_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Return an object's element-set history, newest epoch first."""
    sql = (
        "SELECT object_id, epoch, data_source, mean_motion, eccentricity, inclination, "
        "       ra_of_asc_node, arg_of_pericenter, mean_anomaly, bstar, "
        "       semimajor_axis_km, period_min, apoapsis_km, periapsis_km "
        "FROM gp_history WHERE object_id = :oid ORDER BY epoch DESC"
    )
    params: dict[str, Any] = {"oid": object_id}
    if limit is not None:
        sql += " LIMIT :lim"
        params["lim"] = int(limit)
    async with get_engine().connect() as conn:
        result = await conn.execute(text(sql), params)
        return [dict(row) for row in result.mappings()]
