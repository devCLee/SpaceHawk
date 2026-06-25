"""TEME -> ECEF -> geodetic transforms, matching satellite.js conventions.

Kept deliberately close to satellite.js (``gstime``, ``eciToEcf``,
``eciToGeodetic``) so the authoritative server position and the browser's
display position agree to within tolerance (dev-plan §4.2). Polar motion and
nutation are ignored (display-grade); Stage 2+ can swap in a higher-fidelity
frame conversion without changing callers.
"""

from __future__ import annotations

import math

# WGS-84 ellipsoid (km), as used by satellite.js.
_A = 6378.137
_B = 6356.7523142
_F = (_A - _B) / _A
_E2 = 2 * _F - _F * _F


def gmst_rad(jd_ut1: float) -> float:
    """Greenwich Mean Sidereal Time [rad] from a UT1 Julian date.

    IAU-1982 polynomial (the one satellite.js' ``gstime`` uses).
    """
    t = (jd_ut1 - 2451545.0) / 36525.0
    seconds = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    # seconds of time -> radians (86400 s == 2π)
    g = math.fmod(math.radians(seconds / 240.0), 2 * math.pi)
    return g + 2 * math.pi if g < 0 else g


def teme_to_ecef(r_teme: tuple[float, float, float], gmst: float) -> tuple[float, float, float]:
    """Rotate a TEME position about +Z by GMST into an Earth-fixed frame."""
    x, y, z = r_teme
    cos_g, sin_g = math.cos(gmst), math.sin(gmst)
    return (cos_g * x + sin_g * y, -sin_g * x + cos_g * y, z)


def ecef_to_geodetic(r_ecef: tuple[float, float, float]) -> tuple[float, float, float]:
    """ECEF (km) -> (lat_deg, lon_deg, alt_km), WGS-84.

    Iterative latitude solution identical to satellite.js ``eciToGeodetic``.
    """
    x, y, z = r_ecef
    lon = math.atan2(y, x)
    r = math.sqrt(x * x + y * y)
    lat = math.atan2(z, r)
    c = 1.0
    for _ in range(20):
        c = 1.0 / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + _A * c * _E2 * math.sin(lat), r)
    alt = r / math.cos(lat) - _A * c
    return (math.degrees(lat), math.degrees(lon), alt)


def teme_to_geodetic(
    r_teme: tuple[float, float, float], jd_ut1: float
) -> tuple[float, float, float]:
    """Convenience: TEME (km) + UT1 JD -> (lat_deg, lon_deg, alt_km)."""
    return ecef_to_geodetic(teme_to_ecef(r_teme, gmst_rad(jd_ut1)))
