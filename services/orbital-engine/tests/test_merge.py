"""Multi-source merge/dedup policy."""

from __future__ import annotations

from datetime import datetime

from orbital_engine.domain.space_object import DataSource, SpaceObject
from orbital_engine.ingestion.merge import merge_objects


def _obj(
    *,
    norad: int = 25544,
    source: DataSource = DataSource.SPACE_TRACK,
    epoch: str = "2024-03-10T12:00:00",
    mean_motion: float = 15.5,
    country: str | None = "US",
    name: str = "ISS (ZARYA)",
) -> SpaceObject:
    return SpaceObject.model_validate(
        {
            "OBJECT_NAME": name,
            "OBJECT_ID": "1998-067A",
            "NORAD_CAT_ID": norad,
            "OBJECT_TYPE": "PAYLOAD",
            "EPOCH": epoch,
            "MEAN_MOTION": mean_motion,
            "ECCENTRICITY": 0.0006,
            "INCLINATION": 51.6,
            "RA_OF_ASC_NODE": 32.1,
            "ARG_OF_PERICENTER": 76.8,
            "MEAN_ANOMALY": 58.0,
            "COUNTRY_CODE": country,
            "data_source": source.value,
        }
    )


def test_dedup_collapses_same_usoid() -> None:
    merged = merge_objects([_obj(), _obj(source=DataSource.CELESTRAK)])
    assert len(merged) == 1
    assert merged[0].object_id == "SH:CAT:000025544"


def test_freshest_epoch_wins_elements() -> None:
    stale = _obj(epoch="2024-03-10T00:00:00", mean_motion=15.50, source=DataSource.SPACE_TRACK)
    fresh = _obj(epoch="2024-03-11T00:00:00", mean_motion=15.59, source=DataSource.CELESTRAK)
    merged = merge_objects([stale, fresh])
    assert merged[0].mean_motion == 15.59  # newer epoch's elements, despite lower source priority


def test_source_priority_breaks_epoch_tie() -> None:
    celes = _obj(mean_motion=15.10, source=DataSource.CELESTRAK)
    strack = _obj(mean_motion=15.20, source=DataSource.SPACE_TRACK)
    # Same epoch -> Space-Track (higher authority) wins.
    merged = merge_objects([celes, strack])
    assert merged[0].mean_motion == 15.20
    assert merged[0].data_source == DataSource.SPACE_TRACK


def test_gap_fill_from_lower_priority_record() -> None:
    winner = _obj(epoch="2024-03-11T00:00:00", country=None, source=DataSource.SPACE_TRACK)
    filler = _obj(epoch="2024-03-10T00:00:00", country="PRC", source=DataSource.CELESTRAK)
    merged = merge_objects([winner, filler])
    # Winner kept its fresh elements but borrowed the missing country code.
    assert merged[0].country_code == "PRC"


def test_disjoint_objects_all_retained() -> None:
    a = _obj(norad=11111)
    b = _obj(norad=22222)
    merged = merge_objects([a, b])
    assert {o.norad_cat_id for o in merged} == {11111, 22222}


def test_winner_provenance_not_overwritten() -> None:
    winner = _obj(epoch="2024-03-11T00:00:00", source=DataSource.SPACE_TRACK)
    other = _obj(epoch="2024-03-10T00:00:00", source=DataSource.CELESTRAK)
    merged = merge_objects([winner, other])
    assert merged[0].data_source == DataSource.SPACE_TRACK


def test_epoch_objects_parse() -> None:
    # Guard: helper produces a real datetime epoch (merge sorts on it).
    assert isinstance(_obj().epoch, datetime)
