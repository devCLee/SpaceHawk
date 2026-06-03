"""DISCOS (ESA Database and Information System Characterising Objects in Space).

Stage-2 stub behind the uniform ``SourceAdapter`` interface. DISCOS adds
physical characteristics (size/mass/shape) and launch metadata; it is wired in
fully when its data agreement and offline mirror land (roadmap multi-source
redundancy / P4b). Until configured, ``available()`` is False so the scheduler
skips it without error.
"""

from __future__ import annotations

from typing import ClassVar

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, SpaceObject
from orbital_engine.ingestion.base import SourceAdapter


class DiscosAdapter(SourceAdapter):
    source: ClassVar[DataSource] = DataSource.DISCOS

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def available(self) -> bool:
        return bool(self.settings.discos_api_token)

    async def fetch(self) -> list[SpaceObject]:
        raise NotImplementedError(
            "DISCOS connector is a Stage-2 stub; activation tracked for multi-source/P4b."
        )
