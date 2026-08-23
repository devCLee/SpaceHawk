"""Conjunction screening: candidate pruning -> closest approach -> Pc -> tier.

The engine's own screening (dev-plan §5 Stage 4 / roadmap O2), complementary to
the official CDMs ingested in ``ingestion.cdm``. The expensive all-vs-all step is
pruned cheaply first by an apogee/perigee shell-overlap gate (two objects can
only conjunct where their altitude bands overlap), then surviving candidate pairs
are propagated with the authoritative server SGP4 to find the time and distance
of closest approach. A simplified, explainable probability-of-collision proxy
and the analyst-tunable tier (``severity_for``) finish each record.

The geometry/Pc helpers are pure (operate on SGP4 ``Satrec`` objects and floats)
so they unit-test without a database. ``screen_objects`` orchestrates them over a
batch of catalog rows.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sgp4.api import Satrec, jday

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.conjunction import (
    Conjunction,
    ConjunctionSource,
    TierThresholds,
    estimate_pc,
    make_conjunction_id,
    severity_for,
    usoid_for_norad,
)

# Earth gravitational parameter (km^3/s^2) and equatorial radius (km), WGS-84.
_MU_EARTH = 398600.4418
_R_EARTH = 6378.137


def orbit_altitudes(mean_motion_rev_day: float, eccentricity: float) -> tuple[float, float]:
    """(apogee_alt_km, perigee_alt_km) from mean motion [rev/day] and eccentricity.

    Uses the SGP4 mean motion to recover the semi-major axis (Kepler's third law),
    then apsis altitudes above the equatorial radius. Good enough for a screening
    pre-filter; the precise geometry comes from propagation.
    """
    n_rad_s = mean_motion_rev_day * 2.0 * math.pi / 86400.0
    a = (_MU_EARTH / (n_rad_s * n_rad_s)) ** (1.0 / 3.0)
    return (a * (1.0 + eccentricity) - _R_EARTH, a * (1.0 - eccentricity) - _R_EARTH)


def apogee_perigee_gate(
    apo_a: float, peri_a: float, apo_b: float, peri_b: float, pad_km: float
) -> bool:
    """True if two objects' altitude shells overlap within ``pad_km``.

    A necessary (not sufficient) condition for a conjunction: if the higher
    perigee sits above the lower apogee (plus pad), the bands never meet and the
    pair is pruned before any propagation.
    """
    return max(peri_a, peri_b) <= min(apo_a, apo_b) + pad_km


def _range_km(ra: tuple[float, float, float], rb: tuple[float, float, float]) -> float:
    return math.dist(ra, rb)


def closest_approach(
    sat_a: Satrec,
    sat_b: Satrec,
    jd0: float,
    fr0: float,
    window_sec: float,
    step_sec: float,
) -> tuple[float, float, float | None]:
    """Coarse-then-refine minimum range between two objects over a time window.

    Returns ``(tca_offset_sec, miss_distance_km, relative_speed_km_s)`` where the
    offset is seconds after ``(jd0, fr0)``. ``miss`` is ``inf`` if SGP4 errored at
    every sample. A second finer pass around the coarse minimum sharpens the TCA.
    """

    def sample(offset_sec: float) -> tuple[float, tuple, tuple, tuple] | None:
        fr = fr0 + offset_sec / 86400.0
        err_a, ra, va = sat_a.sgp4(jd0, fr)
        err_b, rb, vb = sat_b.sgp4(jd0, fr)
        if err_a != 0 or err_b != 0:
            return None
        return (_range_km(ra, rb), ra, rb, (va[0] - vb[0], va[1] - vb[1], va[2] - vb[2]))

    def scan(start: float, stop: float, step: float) -> tuple[float, float, tuple | None]:
        best_off, best_rng, best_rel = 0.0, math.inf, None
        t = start
        while t <= stop:
            s = sample(t)
            if s is not None and s[0] < best_rng:
                best_rng, best_rel = s[0], s[3]
                best_off = t
            t += step
        return best_off, best_rng, best_rel

    coarse_off, coarse_rng, _ = scan(0.0, window_sec, step_sec)
    if math.isinf(coarse_rng):
        return (0.0, math.inf, None)
    fine_off, fine_rng, fine_rel = scan(
        max(0.0, coarse_off - step_sec), coarse_off + step_sec, max(1.0, step_sec / 20.0)
    )
    rel_speed = math.dist(fine_rel, (0.0, 0.0, 0.0)) if fine_rel is not None else None
    return (fine_off, fine_rng, rel_speed)


def _build_satrec(row: dict[str, Any]) -> Satrec | None:
    l1, l2 = row.get("tle_line1"), row.get("tle_line2")
    if not l1 or not l2:
        return None
    try:
        return Satrec.twoline2rv(l1, l2)
    except Exception:  # noqa: BLE001 - a malformed TLE just drops the object
        return None


def relative_speed_at(sat_a: Satrec, sat_b: Satrec, when: datetime) -> float | None:
    """|v_a − v_b| in km/s at ``when``; None when SGP4 errors for either object."""
    if when.tzinfo is not None:
        when = when.astimezone(UTC).replace(tzinfo=None)
    jd, fr = jday(
        when.year, when.month, when.day,
        when.hour, when.minute, when.second + when.microsecond / 1e6,
    )
    err_a, _ra, va = sat_a.sgp4(jd, fr)
    err_b, _rb, vb = sat_b.sgp4(jd, fr)
    if err_a != 0 or err_b != 0:
        return None
    return math.dist(va, vb)


def enrich_relative_speed(
    conjunctions: list[Conjunction], rows: list[dict[str, Any]]
) -> int:
    """Fill missing ``relative_speed_km_s`` on conjunctions from catalog TLEs.

    Space-Track's public ``cdm_public`` feed carries no relative-velocity block,
    so CDM-sourced rows arrive without a relative speed. Compute |v1 − v2| at TCA
    by propagating both participants' catalog TLEs. Best-effort, in place: a
    conjunction stays None when either participant has no usable TLE. Returns the
    number of conjunctions enriched.
    """
    by_norad = {
        int(r["norad_cat_id"]): r for r in rows if r.get("norad_cat_id") is not None
    }
    sats: dict[int, Satrec | None] = {}

    def sat_for(norad: int | None) -> Satrec | None:
        if norad is None:
            return None
        if norad not in sats:
            row = by_norad.get(norad)
            sats[norad] = _build_satrec(row) if row else None
        return sats[norad]

    enriched = 0
    for c in conjunctions:
        if c.relative_speed_km_s is not None:
            continue
        sat_a = sat_for(c.primary_norad_cat_id)
        sat_b = sat_for(c.secondary_norad_cat_id)
        if sat_a is None or sat_b is None:
            continue
        speed = relative_speed_at(sat_a, sat_b, c.tca)
        if speed is not None:
            c.relative_speed_km_s = speed
            enriched += 1
    return enriched


def _prep(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a Satrec + apsis altitudes to each usable row (others dropped)."""
    prepped: list[dict[str, Any]] = []
    for row in rows:
        sat = _build_satrec(row)
        mm, ecc = row.get("mean_motion"), row.get("eccentricity")
        if sat is None or mm is None or ecc is None:
            continue
        apo, peri = orbit_altitudes(float(mm), float(ecc))
        prepped.append({**row, "_sat": sat, "_apo": apo, "_peri": peri})
    return prepped


def _candidate_pairs(
    prepped: list[dict[str, Any]], protected_ids: set[int]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pairs to screen: each protected asset vs all others, else full all-vs-all."""
    if protected_ids:
        protected = [r for r in prepped if r.get("norad_cat_id") in protected_ids]
        others = [r for r in prepped if r.get("norad_cat_id") not in protected_ids]
        return [(p, o) for p in protected for o in others]
    return [
        (prepped[i], prepped[j])
        for i in range(len(prepped))
        for j in range(i + 1, len(prepped))
    ]


def _conjunction_from_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    tca: datetime,
    miss_km: float,
    rel_speed: float | None,
    settings: Settings,
    thresholds: TierThresholds,
) -> Conjunction:
    pc = estimate_pc(miss_km, settings.conjunction_pc_sigma_km, settings.conjunction_hard_body_radius_km)
    a_id = a.get("object_id") or usoid_for_norad(a.get("norad_cat_id"), fallback="SH:UNK:A")
    b_id = b.get("object_id") or usoid_for_norad(b.get("norad_cat_id"), fallback="SH:UNK:B")
    return Conjunction(
        id=make_conjunction_id(
            source=ConjunctionSource.SCREENING,
            cdm_id=None,
            primary_object_id=a_id,
            secondary_object_id=b_id,
            tca=tca,
        ),
        source=ConjunctionSource.SCREENING,
        primary_object_id=a_id,
        primary_norad_cat_id=a.get("norad_cat_id"),
        primary_name=a.get("object_name") or a_id,
        secondary_object_id=b_id,
        secondary_norad_cat_id=b.get("norad_cat_id"),
        secondary_name=b.get("object_name") or b_id,
        tca=tca,
        miss_distance_km=miss_km,
        relative_speed_km_s=rel_speed,
        probability=pc,
        severity=severity_for(pc, miss_km, thresholds),
    )


def screen_objects(
    rows: list[dict[str, Any]],
    settings: Settings | None = None,
    now: datetime | None = None,
) -> list[Conjunction]:
    """Screen a batch of catalog rows for conjunctions, ranked worst-first.

    Each row needs ``tle_line1``/``tle_line2``, ``mean_motion`` and
    ``eccentricity`` (the apsis gate). Pairs whose altitude shells don't overlap
    are pruned; survivors (capped at ``conjunction_max_pairs``) are propagated and
    kept when the closest approach is within ``conjunction_miss_threshold_km``.
    """
    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    thresholds = settings.tier_thresholds()
    window_sec = settings.conjunction_screen_window_hours * 3600.0
    jd0, fr0 = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond / 1e6)

    prepped = _prep(rows)
    protected = {int(n) for n in settings.protected_norad_ids}
    gated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for a, b in _candidate_pairs(prepped, protected):
        if apogee_perigee_gate(
            a["_apo"], a["_peri"], b["_apo"], b["_peri"], settings.conjunction_gate_pad_km
        ):
            gated.append((a, b))
        if len(gated) >= settings.conjunction_max_pairs:
            break

    conjunctions: list[Conjunction] = []
    for a, b in gated:
        offset, miss, rel = closest_approach(
            a["_sat"], b["_sat"], jd0, fr0, window_sec, float(settings.conjunction_screen_step_sec)
        )
        if math.isinf(miss) or miss > settings.conjunction_miss_threshold_km:
            continue
        tca = now + timedelta(seconds=offset)
        conjunctions.append(
            _conjunction_from_pair(a, b, tca, miss, rel, settings, thresholds)
        )

    conjunctions.sort(key=lambda c: c.miss_distance_km)
    return conjunctions
