"""Δv / RIC decomposition + rule-based purpose classification (Stage 6 feature #11).

Given a detected :class:`~orbital_engine.domain.maneuver.Maneuver` (the element
deltas across the burn), estimate the impulse that produced it, decomposed into
the RIC (Radial / In-track / Cross-track) frame, and assign a rule-based purpose
class. Everything here is closed-form, first-order orbital mechanics — pure,
explainable, and NumPy-free (the minimal-dependency decision). The estimates are
"good enough" (the roadmap KPI is Δv within ~20%); a high-fidelity estimator is
gated to the Orekit work (dev-plan §3 feature #21).

Approximations (small impulse on a near-circular orbit), with v = sqrt(μ/a):

* **In-track** changes the energy / semi-major axis: ``Δv_t ≈ (v / 2a) · Δa``.
* **Cross-track** rotates the orbit plane by ``Δθ ≈ √(Δi² + (ΔΩ·sin i)²)``
  (radians): ``Δv_c ≈ v · Δθ``.
* **Radial** reshapes eccentricity: ``Δv_r ≈ (v / 2) · Δe`` (magnitude; the mean
  elements do not pin its sign).

RPO is *not* assigned here — it needs a target asset's geometry, owned by the
co-planar RPO monitor (feature #12). This classifier emits the single-object
operational classes and leaves the rest ``UNKNOWN`` rather than guessing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.maneuver import Maneuver, ManeuverType

_MU_EARTH = 398600.4418  # km^3/s^2, WGS-84


def orbital_speed_km_s(sma_km: float) -> float:
    """Circular-orbit speed [km/s] at semi-major axis ``sma_km``."""
    return math.sqrt(_MU_EARTH / sma_km)


@dataclass(frozen=True)
class DeltaV:
    """RIC components and total magnitude, all in m/s."""

    radial: float
    in_track: float
    cross_track: float

    @property
    def total(self) -> float:
        return math.sqrt(self.radial**2 + self.in_track**2 + self.cross_track**2)


def estimate_delta_v(m: Maneuver) -> DeltaV:
    """First-order RIC Δv [m/s] from the maneuver's element deltas."""
    if not m.sma_before_km or m.sma_before_km <= 0.0:
        return DeltaV(0.0, 0.0, 0.0)
    a = m.sma_before_km
    v = orbital_speed_km_s(a)  # km/s
    inc_rad = math.radians(m.inclination_deg or 0.0)

    in_track = (v / (2.0 * a)) * m.delta_sma_km  # signed: raise => prograde
    radial = (v / 2.0) * m.delta_ecc  # magnitude proxy; sign not determined
    plane_angle = math.hypot(
        math.radians(m.delta_inc_deg),
        math.radians(m.delta_raan_deg) * math.sin(inc_rad),
    )
    cross_track = math.copysign(v * plane_angle, m.delta_inc_deg or 1.0)

    return DeltaV(radial=radial * 1000.0, in_track=in_track * 1000.0, cross_track=cross_track * 1000.0)


def classify_type(dv: DeltaV, delta_sma_km: float, settings: Settings) -> ManeuverType:
    """Rule-based purpose from the Δv direction + magnitude. Explainable + total."""
    if dv.total < settings.maneuver_station_keeping_dv_m_s:
        return ManeuverType.STATION_KEEPING
    components = {"in": abs(dv.in_track), "cross": abs(dv.cross_track), "radial": abs(dv.radial)}
    dominant = max(components, key=components.get)
    if dominant == "in":
        if abs(delta_sma_km) >= settings.maneuver_orbit_change_min_dsma_km:
            return ManeuverType.ORBIT_RAISE if delta_sma_km > 0 else ManeuverType.ORBIT_LOWER
        return ManeuverType.PHASING
    # Cross-track (plane change) or radial (eccentricity shaping) dominant: outside
    # the single-object operational set — left UNKNOWN rather than mislabelled.
    return ManeuverType.UNKNOWN


def classify_maneuver(m: Maneuver, settings: Settings | None = None) -> Maneuver:
    """Return a copy of ``m`` enriched with its Δv / RIC estimate and purpose class."""
    settings = settings or get_settings()
    dv = estimate_delta_v(m)
    return m.model_copy(
        update={
            "delta_v_m_s": dv.total,
            "ric_radial_m_s": dv.radial,
            "ric_in_track_m_s": dv.in_track,
            "ric_cross_track_m_s": dv.cross_track,
            "maneuver_type": classify_type(dv, m.delta_sma_km, settings),
        }
    )
