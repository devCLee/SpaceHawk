"""Canonical maneuver model (Stage 6 / roadmap P2a, dev-plan §5 Stage 6 feature #10).

A *maneuver* is a detected, abrupt change in an object's mean orbital elements
between two consecutive element sets in ``gp_history`` — the signature of a
deliberate burn rather than natural perturbation (drag/J2). Detection itself
lives in ``orbital_engine.maneuver``; this module is the language-neutral record
the persistence layer, API, and explainability UI all treat uniformly (the same
discipline as ``domain.conjunction``).

The record is deliberately *explainable* (roadmap O4): it carries the per-element
deltas across the transition and the robust detection statistic that flagged it,
so an analyst can see *why* the engine called a maneuver — not a black-box score.

Δv / RIC decomposition and rule-based purpose classification (feature #11) extend
this record in a later migration; this stage delivers the detection substrate.
"""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# Earth gravitational parameter (km^3/s^2), WGS-84 — shared with screening.py.
_MU_EARTH = 398600.4418


def semimajor_axis_km(mean_motion_rev_day: float) -> float:
    """Semi-major axis [km] from SGP4 mean motion [rev/day] via Kepler's third law."""
    n_rad_s = mean_motion_rev_day * 2.0 * math.pi / 86400.0
    return (_MU_EARTH / (n_rad_s * n_rad_s)) ** (1.0 / 3.0)


def make_maneuver_id(object_id: str, epoch_after: datetime) -> str:
    """Stable id so re-detecting the same event upserts instead of duplicating.

    Keyed on the object and the post-maneuver epoch (to the second): a re-run over
    overlapping history lands the same burn on the same row.
    """
    return f"MNV:{object_id}:{epoch_after.strftime('%Y%m%dT%H%M%S')}"


class Maneuver(BaseModel):
    """One detected element-set transition flagged as a maneuver.

    ``epoch_before`` / ``epoch_after`` bracket the burn (it occurred somewhere in
    that interval; ``detected_epoch`` is the interval midpoint used for ordering).
    The ``delta_*`` fields are post − pre element changes; ``detection_statistic``
    is the robust z-score (deviations from the drag baseline) that crossed the
    threshold, and ``confidence`` is its bounded [0,1] mapping for the UI.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str
    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    epoch_before: datetime
    epoch_after: datetime
    detected_epoch: datetime
    delta_sma_km: float
    delta_ecc: float
    delta_inc_deg: float
    delta_raan_deg: float
    detection_statistic: float
    confidence: float
    detected_at: datetime | None = None
