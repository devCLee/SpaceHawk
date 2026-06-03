"""End-to-end thin-slice walk (dev-plan Stage 1 integration test).

Exercises the whole data plane against real Postgres + Redis:
  normalize -> upsert -> fetch_catalog -> server SGP4 -> Redis latest-state
  -> region rule -> alert pub/sub.

Skipped automatically when the infra isn't up, so the unit suite still runs in
CI without services. To run it locally:  ``docker compose -f infra/docker-compose.yml up db redis``
then ``alembic upgrade head`` and ``pytest``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from orbital_engine import db, state
from orbital_engine.alerts import RegionMonitor
from orbital_engine.config import Settings
from orbital_engine.ingestion.celestrak import normalize
from orbital_engine.propagation.sgp4_service import propagate_objects
from orbital_engine.repository import fetch_catalog, upsert_objects
from orbital_engine.state import ALERT_CHANNEL, get_client, read_latest_state, write_latest_state

# A real on-orbit object so SGP4 + the canonical model both accept it.
ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"
ISS_TLE = f"ISS (ZARYA)\n{ISS_L1}\n{ISS_L2}\n"
ISS_OMM = {
    "OBJECT_NAME": "ISS (ZARYA)",
    "OBJECT_ID": "1998-067A",
    "NORAD_CAT_ID": 25544,
    "EPOCH": "2024-03-10T12:25:39.999",
    "MEAN_MOTION": 15.50079139,
    "ECCENTRICITY": 0.0006008,
    "INCLINATION": 51.6439,
    "RA_OF_ASC_NODE": 32.1281,
    "ARG_OF_PERICENTER": 76.8618,
    "MEAN_ANOMALY": 58.0505,
    "CLASSIFICATION_TYPE": "U",
}


@pytest.fixture
async def infra_up() -> bool:
    if not (await db.ping() and await state.ping()):
        pytest.skip("Postgres/Redis not available — skipping integration walk")
    return True


async def test_slice_walks_end_to_end(infra_up: bool) -> None:
    # 1. ingest: normalize a fixture and upsert into the canonical catalog.
    objects = normalize([ISS_OMM], ISS_TLE)
    written = await upsert_objects(objects)
    assert written == 1

    # 2. read back the catalog projection used by propagation + the BFF.
    rows = await fetch_catalog(limit=10)
    iss = next(r for r in rows if r["norad_cat_id"] == 25544)
    assert iss["tle_line1"] == ISS_L1

    # 3. server SGP4 over the set, then publish the latest state to Redis.
    states = propagate_objects(rows)
    assert any(s["norad_cat_id"] == 25544 for s in states)
    await write_latest_state({"count": len(states), "objects": states})
    snapshot = await read_latest_state()
    assert snapshot is not None and snapshot["count"] == len(states)

    # 4. alert path: force the ISS state into the ROI and prove a frame fans out.
    monitor = RegionMonitor(Settings())
    iss_state = next(s for s in states if s["norad_cat_id"] == 25544)
    iss_state = {**iss_state, "lat_deg": 37.5, "lon_deg": 127.0}
    alerts = monitor.evaluate([iss_state])
    assert len(alerts) == 1

    pubsub = get_client().pubsub()
    await pubsub.subscribe(ALERT_CHANNEL)
    await pubsub.get_message(timeout=1.0)  # consume the subscribe ack
    await state.publish_alert(alerts[0])
    msg = None
    for _ in range(10):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if msg:
            break
        await asyncio.sleep(0.1)
    await pubsub.unsubscribe(ALERT_CHANNEL)
    await pubsub.aclose()
    assert msg is not None
    assert json.loads(msg["data"])["object_id"] == "SH:CAT:000025544"

    await db.dispose()
    await state.close()
