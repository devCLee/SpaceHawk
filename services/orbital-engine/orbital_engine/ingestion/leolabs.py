"""Leolabs commercial SDA feed.

Stage-2 stub behind the uniform ``SourceAdapter`` interface. Leolabs supplies
low-latency commercial radar-tracked states used as a redundant source against
CSpOC/Celestrak (a roadmap risk control). Wired in fully when its data
agreement and offline mirror land. Until configured, ``available()`` is False
so the scheduler skips it.
"""

from __future__ import annotations

from typing import ClassVar

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, SpaceObject
from orbital_engine.ingestion.base import SourceAdapter


class LeolabsAdapter(SourceAdapter):
    source: ClassVar[DataSource] = DataSource.LEOLABS

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def available(self) -> bool:
        return bool(self.settings.leolabs_api_key and self.settings.leolabs_api_secret)

    async def fetch(self) -> list[SpaceObject]:
        raise NotImplementedError(
            "Leolabs connector is a Stage-2 stub; activation tracked for multi-source redundancy."
        )
