"""Propagation accuracy vs a known reference (dev-plan Stage 2 testing).

The authoritative server propagator is checked against the published SGP4
verification vector for catalog object 00005 at epoch (Vallado / sgp4-ver),
and the full propagate_tle path is checked against physical bounds for the ISS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import sqrt

from pytest import approx
from sgp4.api import Satrec

from orbital_engine.propagation.sgp4_service import propagate_tle

# Vallado SGP4 verification case (near-earth), reference TEME state at tsince=0.
VER_L1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
VER_L2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
REF_R = (7022.46529266, -1400.08296755, 0.03995155)  # km, TEME
REF_V = (1.893841015, 6.405893759, 4.534807250)  # km/s, TEME

ISS_L1 = "1 25544U 98067A   24070.51782407  .00006484  00000-0  12035-3 0  9993"
ISS_L2 = "2 25544  51.6439  32.1281 0006008  76.8618  58.0505 15.50079139442263"


def test_sgp4_matches_published_reference_at_epoch() -> None:
    sat = Satrec.twoline2rv(VER_L1, VER_L2)
    err, r, v = sat.sgp4(sat.jdsatepoch, sat.jdsatepochF)
    assert err == 0
    assert r == approx(REF_R, abs=1e-2)  # within 10 m of the published vector
    assert v == approx(REF_V, abs=1e-5)


def test_iss_propagation_within_physical_bounds() -> None:
    # Near the TLE epoch; a LEO payload's geodetic state must be physically sane.
    when = datetime(2024, 3, 10, 12, 25, 40, tzinfo=UTC)
    st = propagate_tle(ISS_L1, ISS_L2, when)
    assert st is not None
    assert st["theory"] == "SGP4"
    assert 380.0 <= st["alt_km"] <= 430.0  # ISS operating altitude band
    assert abs(st["lat_deg"]) <= 51.7  # cannot exceed orbital inclination
    speed = sqrt(sum(c * c for c in st["teme_velocity_km_s"]))
    assert 7.4 <= speed <= 7.8  # LEO circular speed
