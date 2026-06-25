"""Source-adapter interface and registry wiring (no network).

Only element sources are SourceAdapters: Space-Track + Celestrak. DISCOS is an
enrichment source (see tests/test_discos.py); Leolabs is disabled.
"""

from __future__ import annotations

from orbital_engine.config import Settings
from orbital_engine.domain.space_object import DataSource
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.ingestion.celestrak import CelestrakAdapter
from orbital_engine.ingestion.registry import all_adapters, available_adapters


def test_adapters_declare_their_source() -> None:
    assert CelestrakAdapter(Settings()).source is DataSource.CELESTRAK


def test_celestrak_always_available() -> None:
    # Needs no credentials (offline mirror in the enclave).
    assert CelestrakAdapter(Settings()).available() is True


def test_registry_lists_all_known_sources() -> None:
    sources = {a.source for a in all_adapters(Settings())}
    assert sources == {
        DataSource.SPACE_TRACK,
        DataSource.CELESTRAK,
    }


def test_available_adapters_filters_unconfigured() -> None:
    # With no creds, only Celestrak (needs none) is fetchable.
    available = available_adapters(Settings())
    assert [a.source for a in available] == [DataSource.CELESTRAK]


def test_adapters_are_source_adapters() -> None:
    assert all(isinstance(a, SourceAdapter) for a in all_adapters(Settings()))
