"""Leolabs commercial SDA feed — DISABLED.

Leolabs offers no free API token, so the connector cannot be exercised; the
whole adapter is commented out until a paid data agreement lands. It was a
Stage-2 stub behind the uniform ``SourceAdapter`` interface, supplying
low-latency commercial radar-tracked states as a redundant source against
CSpOC/Celestrak (a roadmap risk control). To re-enable: uncomment below, restore
the ``leolabs_*`` settings in orbital_engine/config.py, and re-add the registry
entry in ingestion/registry.py.
"""

# from __future__ import annotations
#
# from typing import ClassVar
#
# from orbital_engine.config import Settings, get_settings
# from orbital_engine.domain.space_object import DataSource, SpaceObject
# from orbital_engine.ingestion.base import SourceAdapter
#
#
# class LeolabsAdapter(SourceAdapter):
#     source: ClassVar[DataSource] = DataSource.LEOLABS
#
#     def __init__(self, settings: Settings | None = None) -> None:
#         self.settings = settings or get_settings()
#
#     def available(self) -> bool:
#         return bool(self.settings.leolabs_api_key and self.settings.leolabs_api_secret)
#
#     async def fetch(self) -> list[SpaceObject]:
#         raise NotImplementedError(
#             "Leolabs connector is a Stage-2 stub; activation tracked for multi-source redundancy."
#         )
