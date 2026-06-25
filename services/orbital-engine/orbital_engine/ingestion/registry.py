"""Source-adapter registry.

The single place that knows which ingestion sources exist. The scheduler and
on-demand ingest call ``available_adapters`` to get the sources configured in
this environment; ``all_adapters`` is for introspection/tests. Space-Track is
the authoritative primary; Celestrak is the redundant/low-latency source.
DISCOS is an enrichment source (physical characteristics patched onto existing
rows; see ingestion/discos.py + repository.apply_enrichments), not a row-creating
adapter, so it is not registered here. Leolabs is disabled (no free API token).
"""

from __future__ import annotations

from orbital_engine.config import Settings, get_settings
from orbital_engine.ingestion.base import SourceAdapter
from orbital_engine.ingestion.celestrak import CelestrakAdapter

# DISCOS is an enrichment source, not a SourceAdapter (see ingestion/discos.py).
# Leolabs disabled (no free API token); adapter commented out in ingestion/leolabs.py.
from orbital_engine.ingestion.spacetrack import SpaceTrackAdapter


def all_adapters(settings: Settings | None = None) -> list[SourceAdapter]:
    """Every known adapter, regardless of whether it is configured.

    Order is source priority (most-authoritative first): Space-Track, then the
    redundant/low-latency Celestrak.
    """
    settings = settings or get_settings()
    return [
        SpaceTrackAdapter(settings),
        CelestrakAdapter(settings),
    ]


def available_adapters(settings: Settings | None = None) -> list[SourceAdapter]:
    """Adapters configured to be fetched in this environment."""
    return [a for a in all_adapters(settings) if a.available()]
