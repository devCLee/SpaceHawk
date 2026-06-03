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
