"""Uniform source-adapter interface for catalog ingestion.

Every data source (Celestrak, Space-Track, DISCOS, Leolabs) implements
``SourceAdapter`` so the scheduler and the merge layer treat them identically.
New feeds (P4b: JCO/ITU/UNOOSA) drop in by adding another adapter — nothing
upstream changes. This is the seam the dev plan (Stage 2) calls for: "keep
source adapters uniform so new feeds drop in later."

``available()`` lets the scheduler skip a source that is not configured in the
current environment — e.g. no Space-Track credentials, or no offline mirror in
the air-gapped enclave — without special-casing it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from orbital_engine.domain.space_object import DataSource, SpaceObject


class SourceAdapter(ABC):
    """A single catalog data source, normalized to canonical ``SpaceObject``s."""

    #: Which provenance this adapter stamps on the records it produces.
    source: ClassVar[DataSource]

    @abstractmethod
    async def fetch(self) -> list[SpaceObject]:
        """Fetch the source's current records and normalize them to canonical objects."""

    def available(self) -> bool:
        """True if this source is configured to be fetched in this environment.

        Default-on; sources that need credentials (Space-Track, DISCOS, Leolabs)
        override this to gate on configuration so the scheduler skips them
        cleanly when unconfigured.
        """
        return True
