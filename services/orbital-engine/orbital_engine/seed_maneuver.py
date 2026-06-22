"""Dev/demo seed: a synthetic maneuvering object so 기동 정보 shows data on boot.

Real maneuver detection needs a multi-epoch ``gp_history`` series that only accrues
as fresh TLEs ingest over days (see ``pipeline.run_ingest_loop``) — too slow for a
demo or a fresh dev box. When ``settings.seed_demo_maneuver`` is set, this inserts
one fictional object whose hand-built element history contains a clean orbit-raise
step, so ``run_maneuver_loop`` flags it on its first cycle and the panel renders an
ORBIT_RAISE for an analyst-tier user.

Gated off by default and rejected in production
(``Settings.assert_secure_for_environment``). Idempotent within a UTC day: epochs
are quantized to midnight and ``append_history`` ignores ``(object_id, epoch)``
conflicts, so restarts don't duplicate rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.space_object import DataSource, ObjectType, SpaceObject
from orbital_engine.logging import get_logger
from orbital_engine.repository import append_history, upsert_objects

log = get_logger("seed.maneuver")

_DEMO_NORAD = 990001
_DEMO_NAME = "SPACEHAWK DEMO MANEUVER"
# Semi-major axis [km] per epoch (oldest -> newest): three steady passes, a +5 km
# orbit raise, then two steady passes. A single >floor step on an otherwise flat
# series is an unambiguous V-pattern: in-track dominant, ΔSMA 5 km >= 2 km =>
# ORBIT_RAISE, Δv ~2.8 m/s. The flat steps keep the robust MAD baseline at zero so
# detect_maneuvers flags exactly the one transition (saturated statistic).
_SMA_SERIES_KM: tuple[float, ...] = (6778.0, 6778.0, 6778.0, 6783.0, 6783.0, 6783.0)


def _demo_object(epoch: datetime, sma_km: float) -> SpaceObject:
    """One element set of the synthetic object at ``epoch`` with the given SMA."""
    return SpaceObject(
        norad_cat_id=_DEMO_NORAD,
        intl_designator="2026-999A",
        object_name=_DEMO_NAME,
        object_type=ObjectType.PAYLOAD,
        data_source=DataSource.CELESTRAK,
        epoch=epoch,
        # Mean elements: detection reads semimajor_axis_km directly (set below), so
        # mean_motion is cosmetic here — a plausible LEO value for completeness.
        mean_motion=15.5,
        eccentricity=0.0007,
        inclination=51.64,
        ra_of_asc_node=120.0,
        arg_of_pericenter=90.0,
        mean_anomaly=0.0,
        bstar=0.0,
        semimajor_axis_km=sma_km,
    )


async def seed_demo_maneuver(settings: Settings | None = None) -> int:
    """Insert the synthetic object + its element history. No-op unless enabled.

    Returns the number of history rows offered (0 when the toggle is off).
    """
    settings = settings or get_settings()
    if not settings.seed_demo_maneuver:
        return 0
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    n = len(_SMA_SERIES_KM)
    history = [
        _demo_object(today - timedelta(days=(n - 1 - i)), sma)
        for i, sma in enumerate(_SMA_SERIES_KM)
    ]
    # Newest element set is the catalog row the maneuver loop fans out over; the
    # full series is the gp_history substrate detection scans.
    await upsert_objects([history[-1]])
    appended = await append_history(history)
    log.info("seed.maneuver", object_id=history[-1].object_id, epochs=appended)
    return appended
