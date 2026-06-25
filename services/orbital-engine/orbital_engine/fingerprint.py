"""Adversary maneuver-behavior fingerprinting (Stage 6 feature #14, the O4 spine).

Builds a per-object *behavioral baseline* from its maneuver history and scores a
new maneuver for *deviation* from that baseline — the program's deliberate,
feasible innovation: bounded novelty on existing TLE-derived data (roadmap O4),
delivered as interpretable statistics rather than an opaque model. ML (HMM /
clustering) is intentionally deferred to Stage 7 as an augment-only layer.

A baseline captures two robust summaries: maneuver *cadence* (median
inter-maneuver interval) and *Δv* (median magnitude), each with its MAD spread,
plus the distribution of purpose classes the object exhibits. A new maneuver is
anomalous when its Δv sits many MADs from the object's norm, or when it is a
purpose class the object has never performed — both reported with the evidence
that triggered them (explainability).

Pure functions over :class:`Maneuver` records; the loop in ``pipeline`` supplies
history from ``repository.query_maneuvers``.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field

from orbital_engine.config import Settings, get_settings
from orbital_engine.domain.maneuver import Maneuver, ManeuverBaseline
from orbital_engine.maneuver import median_abs_deviation

_MAD_TO_SIGMA = 1.4826


def _intervals_days(maneuvers: list[Maneuver]) -> list[float]:
    """Inter-maneuver gaps [days] from time-ordered detection epochs."""
    epochs = sorted(m.detected_epoch for m in maneuvers)
    return [(b - a).total_seconds() / 86400.0 for a, b in zip(epochs, epochs[1:], strict=False)]


def build_baseline(
    maneuvers: list[Maneuver], settings: Settings | None = None
) -> ManeuverBaseline | None:
    """Summarize an object's maneuver history; None if too few to be meaningful."""
    settings = settings or get_settings()
    if len(maneuvers) < settings.fingerprint_min_maneuvers:
        return None
    dvs = [m.delta_v_m_s or 0.0 for m in maneuvers]
    dv_median = statistics.median(dvs)
    intervals = _intervals_days(maneuvers)
    interval_median = statistics.median(intervals) if intervals else None
    interval_mad = median_abs_deviation(intervals, interval_median) if intervals else None
    types = Counter(str(m.maneuver_type) for m in maneuvers)
    return ManeuverBaseline(
        object_id=maneuvers[0].object_id,
        object_name=maneuvers[0].object_name,
        sample_count=len(maneuvers),
        mean_interval_days=interval_median,
        interval_mad_days=interval_mad,
        mean_delta_v_m_s=dv_median,
        delta_v_mad_m_s=median_abs_deviation(dvs, dv_median),
        type_distribution=dict(types),
        last_epoch=max(m.detected_epoch for m in maneuvers),
    )


@dataclass(frozen=True)
class BaselineDeviation:
    """How far a single maneuver departs from its object's baseline."""

    object_id: str
    maneuver_id: str
    delta_v_sigma: float
    novel_type: bool
    is_anomalous: bool
    reasons: list[str] = field(default_factory=list)


def score_deviation(
    baseline: ManeuverBaseline, maneuver: Maneuver, settings: Settings | None = None
) -> BaselineDeviation:
    """Score one maneuver against the baseline (robust Δv z-score + novel-class)."""
    settings = settings or get_settings()
    dv = maneuver.delta_v_m_s or 0.0
    scaled_mad = _MAD_TO_SIGMA * baseline.delta_v_mad_m_s
    diff = abs(dv - baseline.mean_delta_v_m_s)
    if scaled_mad > 0.0:
        dv_sigma = diff / scaled_mad
    else:
        # No Δv spread in the baseline: fall back to a relative jump scaled so a
        # departure of one "floor" reads as the threshold (and larger departures
        # scale past it), avoiding the MAD==0 infinite-sensitivity trap.
        floor = max(1.0, 0.5 * baseline.mean_delta_v_m_s)
        dv_sigma = settings.fingerprint_deviation_sigma * (diff / floor)

    novel_type = str(maneuver.maneuver_type) not in baseline.type_distribution

    reasons: list[str] = []
    if dv_sigma >= settings.fingerprint_deviation_sigma:
        reasons.append(
            f"Δv {dv:.1f} m/s is {dv_sigma:.1f}σ from baseline "
            f"{baseline.mean_delta_v_m_s:.1f} m/s"
        )
    if novel_type:
        reasons.append(f"first observed {maneuver.maneuver_type} maneuver for this object")
    return BaselineDeviation(
        object_id=maneuver.object_id,
        maneuver_id=maneuver.id,
        delta_v_sigma=dv_sigma,
        novel_type=novel_type,
        is_anomalous=bool(reasons),
        reasons=reasons,
    )
