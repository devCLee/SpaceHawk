"""Debris collision-risk scoring (dashboard-grade, explainable — not ORDEM/MASTER).

A per-object risk score in [0, 100] is the product of three normalized factors,
each derived from the object's TLE-mean orbit + size:

  * **Density** ``Dn`` — the debris spatial-density of the object's altitude shell.
    Peaks at the well-known LEO maxima (~750-1000 km primary, ~1400 km secondary)
    and falls off where atmospheric drag clears debris fast (< 500 km) or where
    little is catalogued (MEO/GEO).
  * **Velocity** ``Vn`` — orbital speed as a proxy for impact energy (higher in
    dense LEO, lower in MEO/GEO).
  * **Size** ``Sn`` — RCS size class (a large fragment is both a bigger target and
    a bigger debris generator on impact).

``score = 100 · Dn · Vn · Sn``; the score buckets into Critical/High/Medium/Low.
This mirrors the client-side model in ``apps/web/src/app/data/debrisRisk.ts`` so
the engine and the bundled-snapshot fallback agree. Deliberately transparent and
analyst-tunable — the absolute number is a relative-risk index, not a physical
probability of collision (that comes from ``screening.estimate_pc`` over real
closest approaches).
"""

from __future__ import annotations

import math

# Earth gravitational parameter (km^3/s^2) and equatorial radius (km), WGS-84 —
# matches screening.py so apsis/speed derivations stay consistent across the engine.
_MU_EARTH = 398600.4418
_R_EARTH = 6378.137

#: Risk levels, ascending. Order is shared with the web RISK_ORDER.
RISK_LEVELS: tuple[str, str, str, str] = ("Low", "Medium", "High", "Critical")


def density_factor(mean_altitude_km: float) -> float:
    """Debris spatial-density factor in [0, 1] for a circular-equivalent altitude."""
    h = mean_altitude_km
    if 750.0 <= h <= 1000.0:
        return 1.0  # primary LEO debris peak (densest shell)
    if 1300.0 <= h <= 1500.0:
        return 0.8  # secondary ~1400 km peak
    if 600.0 <= h < 750.0 or 1000.0 < h < 1300.0:
        return 0.6
    if 500.0 <= h < 600.0 or 1500.0 < h <= 2000.0:
        return 0.35
    if 350.0 <= h < 500.0:
        return 0.2  # drag clears this band quickly
    if h > 2000.0:
        return 0.15  # MEO / above the LEO debris belt
    return 0.1  # < 350 km (decaying) or near-GEO tail handled by the > 2000 branch


def velocity_factor(speed_km_s: float) -> float:
    """Orbital-speed factor in [0, 1] (≈1 in dense LEO, lower in MEO/GEO)."""
    return max(0.0, min(1.0, speed_km_s / 8.0))


def size_factor(rcs_size: str | None) -> float:
    """RCS size-class factor; UNKNOWN (the CelesTrak-GP common case) is the midpoint."""
    return {"LARGE": 1.0, "MEDIUM": 0.6, "SMALL": 0.3}.get((rcs_size or "").upper(), 0.5)


def circular_speed_km_s(mean_altitude_km: float) -> float:
    """Circular orbital speed [km/s] at a given mean altitude (vis-viva, e≈0)."""
    a = mean_altitude_km + _R_EARTH
    return math.sqrt(_MU_EARTH / a)


def risk_score(
    mean_altitude_km: float, speed_km_s: float, rcs_size: str | None
) -> float:
    """0-100 risk index = 100 · Dn · Vn · Sn (rounded to 0.1)."""
    score = (
        100.0
        * density_factor(mean_altitude_km)
        * velocity_factor(speed_km_s)
        * size_factor(rcs_size)
    )
    return round(score, 1)


def risk_level(score: float) -> str:
    """Bucket a 0-100 score into Critical/High/Medium/Low."""
    if score >= 70.0:
        return "Critical"
    if score >= 45.0:
        return "High"
    if score >= 20.0:
        return "Medium"
    return "Low"
