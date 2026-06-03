"""gp_history append: row projection (unit) + DB round-trip (infra-gated)."""

from __future__ import annotations

import pytest

from orbital_engine import db, state
from orbital_engine.domain.space_object import SpaceObject
from orbital_engine.repository import (
    _HISTORY_COLUMNS,
    _to_history_row,
    append_history,
    fetch_history,
    upsert_objects,
)

ISS = SpaceObject.model_validate(
    {
        "OBJECT_NAME": "ISS (ZARYA)",
        "OBJECT_ID": "1998-067A",
        "NORAD_CAT_ID": 25544,
        "OBJECT_TYPE": "PAYLOAD",
        "EPOCH": "2024-03-10T12:25:39.999999",
        "MEAN_MOTION": 15.50079139,
        "ECCENTRICITY": 0.0006008,
        "INCLINATION": 51.6439,
        "RA_OF_ASC_NODE": 32.1281,
        "ARG_OF_PERICENTER": 76.8618,
        "MEAN_ANOMALY": 58.0505,
        "BSTAR": 1.2035e-4,
        "TLE_LINE0": "0 ISS (ZARYA)",
        "TLE_LINE1": "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993",
        "TLE_LINE2": "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263",
    }
)


def test_history_row_projects_only_known_columns() -> None:
    row = _to_history_row(ISS)
    assert set(row) == set(_HISTORY_COLUMNS)
    assert row["object_id"] == "SH:CAT:000025544"
    assert row["mean_motion"] == 15.50079139
    assert row["bstar"] == pytest.approx(1.2035e-4)
    assert row["tle_line1"].startswith("1 25544U")


async def test_append_history_empty_is_noop() -> None:
    assert await append_history([]) == 0


# --- infra-gated round-trip (mirrors the Stage-1 integration walk) ---


@pytest.fixture
async def infra_up() -> bool:
    if not (await db.ping() and await state.ping()):
        pytest.skip("Postgres/Redis not available — skipping gp_history round-trip")
    return True


async def test_append_then_fetch_history_idempotent(infra_up: bool) -> None:
    await upsert_objects([ISS])  # FK parent must exist first
    assert await append_history([ISS]) == 1

    hist = await fetch_history("SH:CAT:000025544")
    assert len(hist) == 1
    assert hist[0]["mean_motion"] == 15.50079139

    # Re-appending the same (object, epoch) must not duplicate.
    await append_history([ISS])
    hist = await fetch_history("SH:CAT:000025544")
    assert len(hist) == 1

    await db.dispose()
    await state.close()
