"""Ingestion / propagation throughput at catalog scale (dev-plan Stage 2 testing).

Primarily a correctness-at-volume check (the >=10,000-object KPI); the loose
time bounds only guard against pathological (e.g. accidental O(n^2)) regressions
and are generous enough not to be flaky.
"""

from __future__ import annotations

from time import monotonic

from orbital_engine.ingestion.merge import merge_objects
from orbital_engine.ingestion.spacetrack import normalize_gp
from orbital_engine.propagation.sgp4_service import propagate_objects

ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"


def _gp(norad: int) -> dict:
    return {
        "OBJECT_NAME": f"OBJ-{norad}",
        "OBJECT_ID": f"2024-{norad % 1000:03d}A",
        "NORAD_CAT_ID": str(norad),
        "OBJECT_TYPE": "PAYLOAD",
        "EPOCH": "2024-03-10T12:00:00",
        "CREATION_DATE": "2024-03-10 18:00:00",
        "MEAN_MOTION": "15.5",
        "ECCENTRICITY": "0.0006",
        "INCLINATION": "51.6",
        "RA_OF_ASC_NODE": "32.1",
        "ARG_OF_PERICENTER": "76.8",
        "MEAN_ANOMALY": "58.0",
    }


def test_normalize_and_merge_10k_unique() -> None:
    records = [_gp(10_000 + i) for i in range(10_000)]
    start = monotonic()
    objects = normalize_gp(records)
    merged = merge_objects(objects)
    elapsed = monotonic() - start
    assert len(objects) == 10_000
    assert len(merged) == 10_000  # all unique NORAD ids -> no collapse
    assert elapsed < 30.0


def test_merge_collapses_duplicates_at_scale() -> None:
    # 10k records, only 5k distinct objects (each appears twice).
    records = [_gp(20_000 + (i % 5_000)) for i in range(10_000)]
    merged = merge_objects(normalize_gp(records))
    assert len(merged) == 5_000


def test_propagation_throughput() -> None:
    rows = [
        {"object_id": f"SH:CAT:{i:09d}", "tle_line1": ISS_L1, "tle_line2": ISS_L2}
        for i in range(2_000)
    ]
    start = monotonic()
    states = propagate_objects(rows)
    elapsed = monotonic() - start
    assert len(states) == 2_000
    assert all("lat_deg" in s for s in states)
    assert elapsed < 20.0
