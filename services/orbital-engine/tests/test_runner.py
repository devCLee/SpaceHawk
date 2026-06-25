"""Ingestion runner: concurrent fetch, fault isolation, merge, persist (no DB)."""

from __future__ import annotations

import pytest

from orbital_engine.config import Settings
from orbital_engine.domain.space_object import DataSource, SpaceObject
from orbital_engine.ingestion import runner
from orbital_engine.ingestion.base import SourceAdapter


def _obj(norad: int, source: DataSource, epoch: str = "2024-03-10T12:00:00") -> SpaceObject:
    return SpaceObject.model_validate(
        {
            "OBJECT_NAME": f"OBJ-{norad}",
            "OBJECT_ID": f"1998-{norad:03d}A",
            "NORAD_CAT_ID": norad,
            "OBJECT_TYPE": "PAYLOAD",
            "EPOCH": epoch,
            "MEAN_MOTION": 15.5,
            "ECCENTRICITY": 0.0006,
            "INCLINATION": 51.6,
            "RA_OF_ASC_NODE": 32.1,
            "ARG_OF_PERICENTER": 76.8,
            "MEAN_ANOMALY": 58.0,
            "data_source": source.value,
        }
    )


class _FakeAdapter(SourceAdapter):
    def __init__(self, source: DataSource, objects=None, *, error: Exception | None = None) -> None:
        self.source = source
        self._objects = objects or []
        self._error = error

    async def fetch(self) -> list[SpaceObject]:
        if self._error is not None:
            raise self._error
        return self._objects


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace persistence with capture so the runner needs no DB."""
    box: dict = {"upserted": None, "history": None}

    async def fake_upsert(objects):
        box["upserted"] = objects
        return len(objects)

    async def fake_history(objects):
        box["history"] = objects
        return len(objects)

    monkeypatch.setattr(runner, "upsert_objects", fake_upsert)
    monkeypatch.setattr(runner, "append_history", fake_history)
    return box


async def test_ingest_sources_merges_and_persists(captured: dict) -> None:
    adapters = [
        _FakeAdapter(DataSource.SPACE_TRACK, [_obj(1, DataSource.SPACE_TRACK)]),
        _FakeAdapter(DataSource.CELESTRAK, [_obj(2, DataSource.CELESTRAK)]),
    ]
    summary = await runner.ingest_sources(adapters)
    assert summary == {"sources": 2, "fetched": 2, "written": 2}
    assert {o.norad_cat_id for o in captured["upserted"]} == {1, 2}
    assert captured["history"] is not None  # history appended too


async def test_failing_source_is_isolated(captured: dict) -> None:
    adapters = [
        _FakeAdapter(DataSource.SPACE_TRACK, error=RuntimeError("space-track down")),
        _FakeAdapter(DataSource.CELESTRAK, [_obj(2, DataSource.CELESTRAK)]),
    ]
    summary = await runner.ingest_sources(adapters)
    # The good source still lands; the failed one is skipped, not fatal.
    assert summary["fetched"] == 1
    assert summary["written"] == 1
    assert {o.norad_cat_id for o in captured["upserted"]} == {2}


async def test_dedup_across_sources(captured: dict) -> None:
    # Same object from two sources collapses to one canonical record.
    adapters = [
        _FakeAdapter(DataSource.SPACE_TRACK, [_obj(7, DataSource.SPACE_TRACK)]),
        _FakeAdapter(DataSource.CELESTRAK, [_obj(7, DataSource.CELESTRAK)]),
    ]
    summary = await runner.ingest_sources(adapters)
    assert summary["fetched"] == 2
    assert summary["written"] == 1


async def test_empty_adapter_list_is_noop() -> None:
    assert await runner.ingest_sources([]) == {"sources": 0, "fetched": 0, "written": 0}


async def test_ingest_one_filters_to_requested_available_source(captured: dict) -> None:
    # No creds -> only Celestrak is available; requesting Space-Track ingests nothing.
    settings = Settings()
    assert (await runner.ingest_one(DataSource.SPACE_TRACK.value, settings))["sources"] == 0


async def test_ingest_redundant_excludes_spacetrack(
    captured: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Space-Track's class/gp is capped at 1/hour and owned by the hourly beat, so
    # the sub-hourly accrual loop must skip it. Even when Space-Track is available,
    # ingest_redundant fetches only the redundant sources (Celestrak here).
    adapters = [
        _FakeAdapter(DataSource.SPACE_TRACK, [_obj(1, DataSource.SPACE_TRACK)]),
        _FakeAdapter(DataSource.CELESTRAK, [_obj(2, DataSource.CELESTRAK)]),
    ]
    monkeypatch.setattr(runner, "available_adapters", lambda settings=None: adapters)
    summary = await runner.ingest_redundant(Settings())
    assert summary["sources"] == 1
    assert {o.norad_cat_id for o in captured["upserted"]} == {2}  # Space-Track skipped
