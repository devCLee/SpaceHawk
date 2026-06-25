"""SGP4/SDP4 theory tagging (unit) + per-object Redis state cache (Redis-gated)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orbital_engine import state
from orbital_engine.propagation.sgp4_service import propagate_objects, propagate_tle
from orbital_engine.state import OBJECT_STATE_PREFIX, get_client, read_object_state, write_object_states

WHEN = datetime(2024, 3, 11, 0, 0, 0, tzinfo=UTC)

# Near-earth LEO -> SGP4.
ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"

# Deep-space (period >= 225 min): a GPS bird (~12h, ~2 rev/day) -> SDP4.
GPS_L1 = "1 24876U 97035A   24070.50000000 -.00000045  00000-0  00000-0 0  9992"
GPS_L2 = "2 24876  55.5000 200.0000 0050000  60.0000 300.0000  2.00560000 99999"


def test_theory_is_sgp4_for_near_earth() -> None:
    st = propagate_tle(ISS_L1, ISS_L2, WHEN)
    assert st is not None
    assert st["theory"] == "SGP4"


def test_theory_is_sdp4_for_deep_space() -> None:
    st = propagate_tle(GPS_L1, GPS_L2, WHEN)
    assert st is not None
    assert st["theory"] == "SDP4"


def test_propagate_objects_carries_theory_and_id() -> None:
    rows = [{"object_id": "SH:CAT:000025544", "tle_line1": ISS_L1, "tle_line2": ISS_L2}]
    states = propagate_objects(rows, WHEN)
    assert states[0]["object_id"] == "SH:CAT:000025544"
    assert states[0]["theory"] == "SGP4"


# --- Redis-gated cache round-trip ---


@pytest.fixture
async def redis_up() -> bool:
    if not await state.ping():
        pytest.skip("Redis not available — skipping per-object state cache test")
    return True


async def test_write_and_read_object_state_with_ttl(redis_up: bool) -> None:
    states = [
        {"object_id": "SH:CAT:000025544", "lat_deg": 1.0, "lon_deg": 2.0, "alt_km": 420.0},
        {"object_id": None},  # skipped: no id
    ]
    written = await write_object_states(states, ttl_sec=30)
    assert written == 1

    got = await read_object_state("SH:CAT:000025544")
    assert got is not None and got["alt_km"] == 420.0

    ttl = await get_client().ttl(f"{OBJECT_STATE_PREFIX}SH:CAT:000025544")
    assert 0 < ttl <= 30

    await get_client().delete(f"{OBJECT_STATE_PREFIX}SH:CAT:000025544")
    await state.close()


async def test_read_missing_object_state_is_none(redis_up: bool) -> None:
    assert await read_object_state("SH:CAT:000000000") is None
    await state.close()
