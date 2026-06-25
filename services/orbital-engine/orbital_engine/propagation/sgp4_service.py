"""Authoritative server-side SGP4 propagation.

Uses python-sgp4 (the reference C++ port) on the *same* TLE lines the browser
uses. Returns a compact state dict per object: TEME position/velocity plus the
derived geodetic sub-point used by the trivial region alert and the display.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sgp4.api import Satrec, jday

from orbital_engine.propagation.coordinates import gmst_rad, teme_to_geodetic


def propagate_tle(line1: str, line2: str, when: datetime) -> dict[str, Any] | None:
    """Propagate one TLE to ``when`` (UTC). None if the propagator reports an error.

    python-sgp4 selects SGP4 (near-earth) vs SDP4 (deep-space, period >= 225 min)
    from the element set itself; ``Satrec.method`` ('n'/'d') reports which ran, so
    the catalog covers both regimes with one call. We surface it as ``theory``.
    """
    sat = Satrec.twoline2rv(line1, line2)
    t = when.astimezone(UTC)
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    err, r, v = sat.sgp4(jd, fr)
    if err != 0:
        return None
    lat, lon, alt = teme_to_geodetic(r, jd + fr)
    return {
        "epoch": t.isoformat(),
        "theory": "SDP4" if sat.method == "d" else "SGP4",
        "teme_position_km": list(r),
        "teme_velocity_km_s": list(v),
        "lat_deg": lat,
        "lon_deg": lon,
        "alt_km": alt,
        # GMST is cheap to carry and lets the client cross-check the frame.
        "gmst_rad": gmst_rad(jd + fr),
    }


def propagate_objects(
    objects: Iterable[dict[str, Any]], when: datetime | None = None
) -> list[dict[str, Any]]:
    """Propagate a set of catalog rows (each with tle_line1/2) to ``when``.

    Rows missing TLE lines or failing SGP4 are skipped (logged by the caller).
    """
    when = when or datetime.now(UTC)
    states: list[dict[str, Any]] = []
    for obj in objects:
        line1, line2 = obj.get("tle_line1"), obj.get("tle_line2")
        if not line1 or not line2:
            continue
        state = propagate_tle(line1, line2, when)
        if state is None:
            continue
        state["object_id"] = obj.get("object_id")
        state["object_name"] = obj.get("object_name")
        state["norad_cat_id"] = obj.get("norad_cat_id")
        states.append(state)
    return states
