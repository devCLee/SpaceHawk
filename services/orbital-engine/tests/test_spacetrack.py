"""Space-Track query-builders, normalization, and adapter (recorded fixtures)."""

from __future__ import annotations

from datetime import datetime

import pytest

from orbital_engine.config import Settings
from orbital_engine.domain.space_object import DataSource
from orbital_engine.ingestion import spacetrack
from orbital_engine.ingestion.spacetrack import (
    SpaceTrackAdapter,
    build_cdm_query,
    build_gp_query,
    build_satcat_query,
    build_tip_query,
    normalize_gp,
)

# A recorded gp record carries OMM mean elements *and* the TLE lines.
GP_ISS = {
    "OBJECT_NAME": "ISS (ZARYA)",
    "OBJECT_ID": "1998-067A",
    "NORAD_CAT_ID": "25544",
    "OBJECT_TYPE": "PAYLOAD",
    "EPOCH": "2024-03-10T12:25:39.999999",
    "CREATION_DATE": "2024-03-10 18:00:00",
    "MEAN_MOTION": "15.50079139",
    "ECCENTRICITY": "0.0006008",
    "INCLINATION": "51.6439",
    "RA_OF_ASC_NODE": "32.1281",
    "ARG_OF_PERICENTER": "76.8618",
    "MEAN_ANOMALY": "58.0505",
    "CLASSIFICATION_TYPE": "U",
    "TLE_LINE0": "0 ISS (ZARYA)",
    "TLE_LINE1": "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993",
    "TLE_LINE2": "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263",
}
GP_OBJ2 = {
    **GP_ISS,
    "OBJECT_NAME": "COSMOS",
    "OBJECT_ID": "1999-025A",
    "NORAD_CAT_ID": "25730",
    "CREATION_DATE": "2024-03-11 06:00:00",
}


def test_build_gp_query_full_set_when_no_watermark() -> None:
    q = build_gp_query()
    assert "/class/gp/" in q
    assert "decay_date/null-val" in q
    assert q.endswith("format/json")


def test_build_gp_query_incremental_uses_creation_date() -> None:
    q = build_gp_query(datetime(2024, 3, 10, 18, 0, 0))
    assert "CREATION_DATE/>2024-03-10 18:00:00" in q
    assert "orderby/CREATION_DATE asc" in q


def test_build_gp_query_applies_limit() -> None:
    assert build_gp_query(limit=50).endswith("limit/50")


def test_other_class_builders_target_right_class() -> None:
    assert "/class/satcat/" in build_satcat_query()
    assert "/class/cdm_public/" in build_cdm_query()
    assert "/class/tip/" in build_tip_query()


def test_normalize_gp_maps_records_to_canonical() -> None:
    objects = normalize_gp([GP_ISS, GP_OBJ2])
    assert len(objects) == 2
    iss = objects[0]
    assert iss.object_id == "SH:CAT:000025544"
    assert iss.data_source == DataSource.SPACE_TRACK
    assert iss.intl_designator == "1998-067A"
    assert iss.tle_line1.startswith("1 25544U")


def test_normalize_gp_skips_invalid_records() -> None:
    bad = {"OBJECT_NAME": "JUNK"}  # missing required elements
    objects = normalize_gp([GP_ISS, bad])
    assert [o.norad_cat_id for o in objects] == [25544]


def test_normalize_gp_respects_limit() -> None:
    assert len(normalize_gp([GP_ISS, GP_OBJ2], limit=1)) == 1


def test_available_requires_identity_and_password() -> None:
    assert SpaceTrackAdapter(Settings()).available() is False
    assert SpaceTrackAdapter(Settings(spacetrack_identity="u")).available() is False
    configured = SpaceTrackAdapter(Settings(spacetrack_identity="u", spacetrack_password="p"))
    assert configured.available() is True


class _FakeClient:
    """Stand-in for SpaceTrackClient: records the `since` it was queried with."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.queried_since: datetime | None = None
        self.closed = False

    async def query_gp(self, since=None, *, limit=None):
        self.queried_since = since
        return self.records

    async def aclose(self) -> None:
        self.closed = True


async def test_fetch_normalizes_and_advances_watermark(monkeypatch: pytest.MonkeyPatch) -> None:
    marker: dict[str, str] = {}

    async def fake_read(source: str):
        return marker.get(source)

    async def fake_write(source: str, ts: str):
        marker[source] = ts

    monkeypatch.setattr(spacetrack, "read_sync_marker", fake_read)
    monkeypatch.setattr(spacetrack, "write_sync_marker", fake_write)

    fake = _FakeClient([GP_ISS, GP_OBJ2])
    adapter = SpaceTrackAdapter(
        Settings(spacetrack_identity="u", spacetrack_password="p"),
        client_factory=lambda: fake,
    )

    objects = await adapter.fetch()

    assert [o.norad_cat_id for o in objects] == [25544, 25730]
    assert fake.closed is True
    assert fake.queried_since is None  # first run: no watermark
    # Watermark advanced to the newest CREATION_DATE in the batch.
    assert marker[DataSource.SPACE_TRACK.value] == "2024-03-11 06:00:00"


async def test_fetch_second_run_queries_incrementally(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = {DataSource.SPACE_TRACK.value: "2024-03-10 18:00:00"}

    async def fake_read(source: str):
        return marker.get(source)

    async def fake_write(source: str, ts: str):
        marker[source] = ts

    monkeypatch.setattr(spacetrack, "read_sync_marker", fake_read)
    monkeypatch.setattr(spacetrack, "write_sync_marker", fake_write)

    fake = _FakeClient([GP_OBJ2])
    adapter = SpaceTrackAdapter(
        Settings(spacetrack_identity="u", spacetrack_password="p"),
        client_factory=lambda: fake,
    )
    await adapter.fetch()
    assert fake.queried_since == datetime(2024, 3, 10, 18, 0, 0)
