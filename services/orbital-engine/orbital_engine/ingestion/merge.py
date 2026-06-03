"""Multi-source de-duplication and merge into one canonical record.

Several feeds describe the same object. The dev plan (Stage 2) requires
"source-priority & de-duplication into one canonical record" so the catalog
holds exactly one row per object. The policy:

  * **Group** by USOID (``object_id``).
  * **Winner = freshest element set.** The record with the newest ``epoch`` wins
    the orbital elements (the thing that actually goes stale). Space-Track
    breaks ties as the authoritative source.
  * **Gap-fill metadata.** Fields the winner leaves null are filled from the
    other records (e.g. DISCOS size/mass, a country code present in only one
    feed) — so merging adds information without overwriting fresher data.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from orbital_engine.domain.space_object import DataSource, SpaceObject

# Lower number = higher authority; used only to break epoch ties.
SOURCE_PRIORITY: dict[str, int] = {
    DataSource.SPACE_TRACK.value: 0,
    DataSource.CELESTRAK.value: 1,
    DataSource.LEOLABS.value: 2,
    DataSource.DISCOS.value: 3,
}
_UNKNOWN_PRIORITY = 99

# Never gap-filled from a lower-priority record: identity/provenance of the winner.
_WINNER_ONLY = frozenset({"object_id", "data_source", "ingested_at"})


def _rank(obj: SpaceObject) -> tuple[Any, int]:
    """Sort key: newest epoch first, then most-authoritative source (with reverse=True)."""
    return (obj.epoch, -SOURCE_PRIORITY.get(obj.data_source, _UNKNOWN_PRIORITY))


def _combine(group: list[SpaceObject]) -> SpaceObject:
    group.sort(key=_rank, reverse=True)
    merged = group[0].model_dump(mode="python")
    for other in group[1:]:
        other_data = other.model_dump(mode="python")
        for field, value in merged.items():
            if value is None and field not in _WINNER_ONLY and other_data.get(field) is not None:
                merged[field] = other_data[field]
    return SpaceObject.model_validate(merged)


def merge_objects(objects: Iterable[SpaceObject]) -> list[SpaceObject]:
    """Collapse records sharing a USOID into one canonical record each.

    Order is stable on first appearance of each USOID, so a caller passing
    sources in priority order gets a predictable result.
    """
    groups: dict[str, list[SpaceObject]] = {}
    for obj in objects:
        groups.setdefault(obj.object_id, []).append(obj)
    return [_combine(group) for group in groups.values()]
