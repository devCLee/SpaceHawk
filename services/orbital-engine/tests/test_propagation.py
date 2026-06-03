"""Server-side propagation + the client/server reconciliation guard (dev-plan §4.2).

The browser (satellite.js) and the server (python-sgp4 here) agree *by
construction* because they propagate the same TLE and use the same GMST
polynomial + WGS-84 iterative geodetic solution. These tests pin that contract:
GMST against an independent reference value, and a sanity envelope on the
propagated ISS sub-point.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from orbital_engine.propagation.coordinates import ecef_to_geodetic, gmst_rad
from orbital_engine.propagation.sgp4_service import propagate_tle

ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"


def test_gmst_matches_j2000_reference() -> None:
    # GMST at J2000.0 (2000-01-01 12:00 UT1) is 280.46061838° — the canonical
    # value satellite.js' gstime reproduces from the same IAU-1982 polynomial.
    expected = math.radians(280.46061838)
    assert abs(gmst_rad(2451545.0) - expected) < 1e-6


def test_ecef_to_geodetic_on_equatorial_axis() -> None:
    # A point on the +X axis at one Earth radius -> lat 0, lon 0, ~0 altitude.
    lat, lon, alt = ecef_to_geodetic((6378.137, 0.0, 0.0))
    assert abs(lat) < 1e-6
    assert abs(lon) < 1e-6
    assert abs(alt) < 1e-6


def test_iss_propagation_envelope() -> None:
    state = propagate_tle(ISS_L1, ISS_L2, datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC))
    assert state is not None
    # Sub-point latitude can never exceed the orbital inclination (~51.6°).
    assert abs(state["lat_deg"]) <= 52.0
    # ISS altitude sits in a tight LEO band.
    assert 350.0 < state["alt_km"] < 450.0
    assert -180.0 <= state["lon_deg"] <= 180.0


def test_propagation_is_deterministic() -> None:
    when = datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC)
    a = propagate_tle(ISS_L1, ISS_L2, when)
    b = propagate_tle(ISS_L1, ISS_L2, when)
    assert a == b
