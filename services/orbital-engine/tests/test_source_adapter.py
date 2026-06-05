"""Source-adapter interface, stubs, and registry wiring (no network)."""

from __future__ import annotations

import pytest

from orbital_engine.config import Settings
from orbital_engine.domain.space_object import DataSource
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.ingestion.celestrak import CelestrakAdapter
from orbital_engine.ingestion.discos import DiscosAdapter

# Leolabs disabled (no free API token); adapter commented out in ingestion/leolabs.py.
# from orbital_engine.ingestion.leolabs import LeolabsAdapter
from orbital_engine.ingestion.registry import all_adapters, available_adapters


def test_adapters_declare_their_source() -> None:
    s = Settings()
    assert CelestrakAdapter(s).source is DataSource.CELESTRAK
    assert DiscosAdapter(s).source is DataSource.DISCOS


def test_celestrak_always_available() -> None:
    # Needs no credentials (offline mirror in the enclave).
    assert CelestrakAdapter(Settings()).available() is True


def test_stubs_unavailable_without_credentials() -> None:
    s = Settings(discos_api_token=None)
    assert DiscosAdapter(s).available() is False


def test_stubs_available_once_configured() -> None:
    assert DiscosAdapter(Settings(discos_api_token="tok")).available() is True


async def test_stub_fetch_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        await DiscosAdapter(Settings(discos_api_token="tok")).fetch()


def test_registry_lists_all_known_sources() -> None:
    sources = {a.source for a in all_adapters(Settings())}
    assert sources == {
        DataSource.SPACE_TRACK,
        DataSource.CELESTRAK,
        DataSource.DISCOS,
    }


def test_available_adapters_filters_unconfigured() -> None:
    # With no creds, only Celestrak (needs none) is fetchable.
    available = available_adapters(Settings())
    assert [a.source for a in available] == [DataSource.CELESTRAK]


def test_adapters_are_source_adapters() -> None:
    assert all(isinstance(a, SourceAdapter) for a in all_adapters(Settings()))
