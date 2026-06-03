"""Celestrak normalization (pure, no network)."""

from __future__ import annotations

from orbital_engine.domain.space_object import DataSource
from orbital_engine.ingestion.celestrak import _parse_tle_text, normalize

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


def test_parse_tle_text_keys_by_norad() -> None:
    parsed = _parse_tle_text(ISS_TLE)
    assert 25544 in parsed
    assert parsed[25544][1] == ISS_L1


def test_normalize_merges_tle_and_derives_usoid() -> None:
    objects = normalize([ISS_OMM], ISS_TLE)
    assert len(objects) == 1
    obj = objects[0]
    assert obj.object_id == "SH:CAT:000025544"
    assert obj.data_source == DataSource.CELESTRAK
    assert obj.tle_line1 == ISS_L1
    assert obj.tle_line2 == ISS_L2


def test_normalize_skips_records_without_tle() -> None:
    # OMM record whose NORAD id has no matching TLE line is dropped (can't propagate).
    objects = normalize([{**ISS_OMM, "NORAD_CAT_ID": 99999}], ISS_TLE)
    assert objects == []


def test_normalize_respects_limit() -> None:
    two = [ISS_OMM, {**ISS_OMM, "NORAD_CAT_ID": 25544, "OBJECT_NAME": "DUP"}]
    assert len(normalize(two, ISS_TLE, limit=1)) == 1
