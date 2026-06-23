"""Observer-based satellite pass prediction over the 대전 KARI ground station (R2).

Feeds report §2/§3 (북한/중국/러시아/일본 위성 한반도 통과 활동). Ported from the
browser's ``apps/web/src/app/utils/lookAngles.ts`` (satellite.js
``ecfToLookAngles`` + ``predictPasses``), reusing the engine's authoritative SGP4
propagation and TEME->ECEF frame so server and client agree by construction.

Pure, deterministic compute: no DB, no network, no LLM. stdlib ``math`` only
(numpy is not an engine dependency). The module returns a geometry-only
:class:`PassGeometry` dataclass and stays decoupled from owner/name lookup — the
R3 assembler maps it onto :class:`SatellitePass` and attaches satellite_name/id.

Pipeline
========

    TLE (line1, line2)
        |
        v   propagate_tle()  -- python-sgp4, TEME position + GMST
    TEME position [km] @ t
        |
        v   teme_to_ecef()   -- rotate about +Z by GMST
    ECEF position [km] @ t
        |
        v   ecef_to_topocentric()  -- ECEF->ENU rotation at the observer
    azimuth [deg], elevation [deg], slant range [km]
        |
        v   sample window @ step_s, gate on elevation >= min_elevation_deg
    contiguous span = one pass; refine the peak for closest approach
        |
        v
    PassGeometry(aos, los, closest_time, closest_distance_km, az, el)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from orbital_engine.propagation.coordinates import (
    _A,
    _E2,
    teme_to_ecef,
)
from orbital_engine.propagation.sgp4_service import propagate_tle


@dataclass(frozen=True)
class Observer:
    """A ground observer (geodetic WGS-84)."""

    lat_deg: float
    lon_deg: float
    alt_km: float


# 대전 KARI ground station. Source: apps/web/src/app/data/sensors.ts
# (id "kari-daejeon": latDeg 36.38, lonDeg 127.36, altKm 0.07).
KARI = Observer(lat_deg=36.38, lon_deg=127.36, alt_km=0.07)


@dataclass(frozen=True)
class PassGeometry:
    """One contiguous pass above the elevation mask (geometry only).

    Closest approach = the sample with maximum elevation (equivalently minimum
    slant range), refined around the coarse-grid peak. The R3 assembler maps
    this onto reports.schemas.SatellitePass and attaches the satellite name/id.
    """

    aos: datetime
    los: datetime
    closest_time: datetime
    closest_distance_km: float
    azimuth_deg: float
    elevation_deg: float


def _observer_ecef(observer: Observer) -> tuple[float, float, float]:
    """Observer geodetic (WGS-84) -> ECEF position [km].

    Standard geodetic-to-ECEF with the prime-vertical radius of curvature
    ``N = a / sqrt(1 - e^2 sin^2(lat))`` (Vallado, *Fundamentals of
    Astrodynamics and Applications*, Algorithm 51).
    """
    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    h = observer.alt_km
    n = _A / math.sqrt(1.0 - _E2 * math.sin(lat) ** 2)
    x = (n + h) * math.cos(lat) * math.cos(lon)
    y = (n + h) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - _E2) + h) * math.sin(lat)
    return (x, y, z)


def ecef_to_topocentric(
    sat_ecef: tuple[float, float, float], observer: Observer
) -> tuple[float, float, float]:
    """ECEF satellite position + observer geodetic -> (azimuth, elevation, range).

    Returns azimuth in [0, 360) deg (clockwise from North), elevation in
    [-90, 90] deg, and slant range in km.

    The line-of-sight vector (sat - observer) is rotated from ECEF into the
    local East-North-Up (ENU) topocentric frame at the observer. With observer
    latitude ``phi`` and longitude ``lam`` (Vallado Algorithm 51 / satellite.js
    ``ecfToLookAngles``)::

        e =       -sin(lam) dx +        cos(lam) dy
        n = -sin(phi)cos(lam) dx - sin(phi)sin(lam) dy + cos(phi) dz
        u =  cos(phi)cos(lam) dx + cos(phi)sin(lam) dy + sin(phi) dz

        range     = |(dx, dy, dz)|
        elevation = asin(u / range)
        azimuth   = atan2(e, n)   (clockwise from North, wrapped to [0, 360))
    """
    obs = _observer_ecef(observer)
    dx = sat_ecef[0] - obs[0]
    dy = sat_ecef[1] - obs[1]
    dz = sat_ecef[2] - obs[2]

    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    rng = math.sqrt(dx * dx + dy * dy + dz * dz)
    elevation = math.degrees(math.asin(up / rng)) if rng > 0 else 0.0
    azimuth = math.degrees(math.atan2(east, north))
    if azimuth < 0.0:
        azimuth += 360.0
    return (azimuth, elevation, rng)


def _look_angle(
    line1: str, line2: str, observer: Observer, when: datetime
) -> tuple[float, float, float] | None:
    """Topocentric (az, el, range) of a TLE from ``observer`` at ``when``, or None.

    None when SGP4 reports an error (mirrors propagate_tle's contract).
    """
    state = propagate_tle(line1, line2, when)
    if state is None:
        return None
    sat_ecef = teme_to_ecef(tuple(state["teme_position_km"]), state["gmst_rad"])
    return ecef_to_topocentric(sat_ecef, observer)


def predict_passes(
    elements: tuple[str, str],
    observer: Observer,
    start: datetime,
    end: datetime,
    *,
    step_s: float = 30.0,
    min_elevation_deg: float = 0.0,
) -> list[PassGeometry]:
    """Predict passes of ``elements`` (TLE line1, line2) over [start, end].

    A pass is a contiguous span where elevation >= ``min_elevation_deg``. For
    each pass we record AOS (first in-mask sample), LOS (last in-mask sample),
    and the closest approach (max elevation / min slant range), refining the
    peak with a finer local scan so the closest time/range are not pinned to the
    coarse grid. Mirrors lookAngles.ts ``predictPasses`` (rise/set/max-elevation
    over a stepped window), extended with range + peak refinement.

    Returns geometry-only ``PassGeometry`` records (assembler attaches name/id).
    Degenerate windows (start >= end, non-positive step) return ``[]``.
    """
    if end <= start or step_s <= 0:
        return []

    line1, line2 = elements
    step = timedelta(seconds=step_s)

    passes: list[PassGeometry] = []
    in_pass = False
    aos: datetime | None = None
    last_in: datetime | None = None
    peak_time: datetime | None = None
    peak_el = -90.0

    t = start
    while t <= end:
        look = _look_angle(line1, line2, observer, t)
        if look is not None:
            _, elevation, _ = look
            if elevation >= min_elevation_deg:
                if not in_pass:
                    in_pass = True
                    aos = t
                    peak_time = t
                    peak_el = elevation
                elif elevation > peak_el:
                    peak_el = elevation
                    peak_time = t
                last_in = t
            elif in_pass and aos is not None and last_in is not None and peak_time is not None:
                passes.append(_finalize(line1, line2, observer, aos, last_in, peak_time, step_s))
                in_pass = False
                aos = last_in = peak_time = None
                peak_el = -90.0
        t += step

    # Close a pass still open at the window edge.
    if in_pass and aos is not None and last_in is not None and peak_time is not None:
        passes.append(_finalize(line1, line2, observer, aos, last_in, peak_time, step_s))

    return passes


def _finalize(
    line1: str,
    line2: str,
    observer: Observer,
    aos: datetime,
    los: datetime,
    coarse_peak: datetime,
    step_s: float,
) -> PassGeometry:
    """Build a PassGeometry, refining the closest approach around the coarse peak.

    Re-scans [coarse_peak - step, coarse_peak + step] at a tenth of the grid
    step and keeps the maximum-elevation (== minimum-range) sample, so the
    closest time/range/az/el are sub-grid accurate rather than on the coarse
    grid. Clamps the refinement window to [aos, los].
    """
    refine_step_s = max(step_s / 10.0, 1.0)
    lo = max(aos, coarse_peak - timedelta(seconds=step_s))
    hi = min(los, coarse_peak + timedelta(seconds=step_s))

    best_time = coarse_peak
    best_az, best_el, best_rng = 0.0, -90.0, math.inf

    t = lo
    while t <= hi:
        look = _look_angle(line1, line2, observer, t)
        if look is not None:
            az, el, rng = look
            if el > best_el:
                best_az, best_el, best_rng, best_time = az, el, rng, t
        t += timedelta(seconds=refine_step_s)

    return PassGeometry(
        aos=aos,
        los=los,
        closest_time=best_time,
        closest_distance_km=best_rng,
        azimuth_deg=best_az,
        elevation_deg=best_el,
    )
