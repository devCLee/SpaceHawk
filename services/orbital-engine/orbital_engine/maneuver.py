"""Maneuver detection: robust V-pattern flag on the element-set history.

Stage 6 / roadmap P2a feature #10 (dev-plan §5 Stage 6): the validated TRL 5-6
detector, ported from REACT's *PREFIL + SGP4 V-pattern* method as original code
(licensing §4.7 — re-implemented from the published method, not lifted).

The substrate is ``gp_history`` — an append-only series of mean elements per
object. A natural orbit decays smoothly (drag lowers the semi-major axis along a
gentle, near-monotonic slope); a deliberate burn shows as an abrupt *step* in
that slope — the "V" in the SMA-vs-time plot. We detect it from the series of
consecutive semi-major-axis first-differences:

  1. PREFIL — pre-filter: an object with too few element sets, or whose total SMA
     span never exceeds the noise floor, cannot yield a defensible detection and
     is skipped before any statistics are computed.
  2. Robust baseline — the median and MAD (median absolute deviation) of the
     first-difference series describe the *normal* per-step drift. MAD is used,
     not standard deviation, so a single large burn does not inflate its own
     baseline and mask itself.
  3. Flag — a step whose deviation from the median exceeds ``k`` scaled-MADs *and*
     an absolute floor (km) is a maneuver. The floor suppresses false positives
     when the baseline noise is ~0 (a perfectly smooth feed), where any tiny
     wobble would otherwise be "infinitely many" MADs out.

Everything here is pure (operates on dicts of floats + datetimes) so it unit-tests
without a database; the loop in ``pipeline`` feeds it ``repository.fetch_history``.
"""

from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.maneuver import Maneuver, make_maneuver_id, semimajor_axis_km
from orbital_engine.maneuver_analysis import classify_maneuver

# Scale factor making the MAD a consistent estimator of the standard deviation for
# normally-distributed data (so ``k`` reads as "k sigma"). 1 / Phi^-1(0.75).
_MAD_TO_SIGMA = 1.4826

# Detection statistic assigned when the robust baseline has zero dispersion but the
# step clears the absolute floor: the jump is unambiguous against a noiseless feed.
_SATURATED_STAT = 999.0


def median_abs_deviation(values: list[float], center: float) -> float:
    """Median absolute deviation of ``values`` about ``center`` (robust spread)."""
    if not values:
        return 0.0
    return statistics.median([abs(v - center) for v in values])


def _series(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Time-ordered (oldest-first) element sets with a usable semi-major axis.

    ``fetch_history`` returns newest-first; detection needs chronological order.
    SMA is taken from the stored column when present, else recovered from mean
    motion (the column is nullable in ``gp_history``).
    """
    ordered = sorted(history, key=lambda h: h["epoch"])
    series: list[dict[str, Any]] = []
    for h in ordered:
        sma = h.get("semimajor_axis_km")
        mm = h.get("mean_motion")
        if sma is None and mm:
            sma = semimajor_axis_km(float(mm))
        if sma is None:
            continue
        series.append({**h, "_sma": float(sma)})
    return series


def _confidence(statistic: float, k: float) -> float:
    """Map the robust z-score onto [0,1]: at the threshold ~0, at 2k ~1."""
    if k <= 0.0:
        return 1.0
    return max(0.0, min(1.0, (statistic - k) / k))


def _maneuver_from_transition(
    before: dict[str, Any],
    after: dict[str, Any],
    statistic: float,
    k: float,
) -> Maneuver:
    epoch_before: datetime = before["epoch"]
    epoch_after: datetime = after["epoch"]
    mid = epoch_before + (epoch_after - epoch_before) / 2
    return Maneuver(
        id=make_maneuver_id(after["object_id"], epoch_after),
        object_id=after["object_id"],
        norad_cat_id=after.get("norad_cat_id"),
        object_name=after.get("object_name") or after["object_id"],
        epoch_before=epoch_before,
        epoch_after=epoch_after,
        detected_epoch=mid,
        delta_sma_km=after["_sma"] - before["_sma"],
        delta_ecc=float(after.get("eccentricity") or 0.0) - float(before.get("eccentricity") or 0.0),
        delta_inc_deg=float(after.get("inclination") or 0.0) - float(before.get("inclination") or 0.0),
        delta_raan_deg=float(after.get("ra_of_asc_node") or 0.0)
        - float(before.get("ra_of_asc_node") or 0.0),
        detection_statistic=statistic,
        confidence=_confidence(statistic, k),
        sma_before_km=before["_sma"],
        inclination_deg=float(after.get("inclination") or 0.0),
    )


def detect_maneuvers(
    history: list[dict[str, Any]],
    settings: Settings | None = None,
) -> list[Maneuver]:
    """Detect maneuvers in one object's element-set history (PREFIL + V-pattern).

    ``history`` is a list of ``gp_history`` rows for a single object (any order;
    each needs ``epoch`` and either ``semimajor_axis_km`` or ``mean_motion``).
    Returns the flagged transitions, ordered by epoch.
    """
    settings = settings or get_settings()
    series = _series(history)

    # PREFIL: need enough points for a baseline, and a span above the floor.
    if len(series) < settings.maneuver_min_history_points:
        return []
    smas = [s["_sma"] for s in series]
    if max(smas) - min(smas) < settings.maneuver_min_delta_sma_km:
        return []

    diffs = [smas[i + 1] - smas[i] for i in range(len(smas) - 1)]
    median = statistics.median(diffs)
    scaled_mad = _MAD_TO_SIGMA * median_abs_deviation(diffs, median)

    k = settings.maneuver_mad_k
    floor = settings.maneuver_min_delta_sma_km
    maneuvers: list[Maneuver] = []
    for i, diff in enumerate(diffs):
        deviation = abs(diff - median)
        if abs(diff) < floor:
            continue  # natural per-step drift — below the absolute floor
        if scaled_mad > 0.0:
            statistic = deviation / scaled_mad
            if statistic < k:
                continue
        else:
            statistic = _SATURATED_STAT  # noiseless baseline, jump clears the floor
        maneuvers.append(_maneuver_from_transition(series[i], series[i + 1], statistic, k))
    # Enrich each detection with its Δv / RIC decomposition + purpose class so the
    # persisted record is analyst-ready (feature #11); detection stays separable.
    return [classify_maneuver(m, settings) for m in maneuvers]
