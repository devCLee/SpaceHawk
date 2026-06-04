"""Canonical conjunction model + trust-calibrated severity tiering.

A conjunction is a close approach between two space objects, sourced either from
an official CCSDS Conjunction Data Message (``cdm_public``) or computed by the
engine's own screening (Stage 4, dev-plan §5 / roadmap O2). Both sources produce
the same canonical record so the API, persistence, and UI treat them uniformly.

Severity tiers are the *analyst-facing confidence* (roadmap O4: trust-calibrated,
explainable), derived from probability-of-collision and miss distance against
analyst-tunable thresholds — deliberately not a black box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from orbital_engine.domain.space_object import make_usoid


class ConjunctionSeverity(StrEnum):
    LOW = "LOW"
    MOD = "MOD"
    HIGH = "HIGH"


class ConjunctionSource(StrEnum):
    CDM = "CDM"
    SCREENING = "SCREENING"


@dataclass(frozen=True)
class TierThresholds:
    """Analyst-tunable cut points for the severity tiers (see config.Settings).

    A conjunction is HIGH if it breaches either HIGH gate, MOD if it breaches a
    MOD gate, else LOW. Probability dominates when present; miss distance is the
    fallback so a missing Pc never downgrades a physically close approach.
    """

    pc_high: float = 1e-4
    pc_mod: float = 1e-6
    miss_high_km: float = 1.0
    miss_mod_km: float = 5.0


DEFAULT_THRESHOLDS = TierThresholds()


def severity_for(
    probability: float | None,
    miss_distance_km: float,
    thresholds: TierThresholds = DEFAULT_THRESHOLDS,
) -> ConjunctionSeverity:
    """Map (Pc, miss distance) onto a severity tier. Explainable and total."""
    pc = probability or 0.0
    if pc >= thresholds.pc_high or miss_distance_km <= thresholds.miss_high_km:
        return ConjunctionSeverity.HIGH
    if pc >= thresholds.pc_mod or miss_distance_km <= thresholds.miss_mod_km:
        return ConjunctionSeverity.MOD
    return ConjunctionSeverity.LOW


def estimate_pc(miss_distance_km: float, sigma_km: float, hard_body_radius_km: float) -> float:
    """Simplified, explainable probability-of-collision proxy for self-screening.

    A real Pc needs both objects' covariances (which CDMs carry but a bare TLE
    does not). For engine-screened events we use the standard small-hard-body
    approximation of a 2-D circular Gaussian miss distribution with combined
    1-sigma ``sigma_km``::

        Pc ~= (HBR^2 / (2 sigma^2)) * exp(-miss^2 / (2 sigma^2))

    Clamped to [0, 1]. It is monotonic (closer => higher Pc) and analyst-tunable
    via ``sigma_km`` / ``hard_body_radius_km`` — deliberately not a black box.
    """
    if sigma_km <= 0.0:
        return 0.0
    pc = (hard_body_radius_km**2 / (2.0 * sigma_km**2)) * math.exp(
        -(miss_distance_km**2) / (2.0 * sigma_km**2)
    )
    return max(0.0, min(1.0, pc))


def make_conjunction_id(
    *,
    source: ConjunctionSource,
    cdm_id: str | None,
    primary_object_id: str,
    secondary_object_id: str,
    tca: datetime,
) -> str:
    """Derive a stable id so re-ingest / re-screen of the same event upserts.

    CDM events are keyed on the official message id; screened events are keyed on
    the ordered object pair and the TCA to the minute (a refined re-screen of the
    same approach lands on the same row instead of duplicating).
    """
    if source is ConjunctionSource.CDM and cdm_id:
        return f"CDM:{cdm_id}"
    a, b = sorted((primary_object_id, secondary_object_id))
    return f"SCR:{a}:{b}:{tca.strftime('%Y%m%dT%H%M')}"


def usoid_for_norad(norad_cat_id: int | None, *, fallback: str) -> str:
    """USOID for a conjunction participant, falling back when uncatalogued."""
    if norad_cat_id is not None:
        return make_usoid(norad_cat_id=norad_cat_id, intl_designator=None)
    return fallback


class Conjunction(BaseModel):
    """One screened or CDM-sourced close approach.

    Field names are the contract the web BFF (`fetchConjunctions`) renders; the
    engine returns these verbatim from ``GET /conjunctions``.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str
    source: ConjunctionSource
    cdm_id: str | None = None
    primary_object_id: str
    primary_norad_cat_id: int | None = None
    primary_name: str
    secondary_object_id: str
    secondary_norad_cat_id: int | None = None
    secondary_name: str
    tca: datetime
    miss_distance_km: float
    relative_speed_km_s: float | None = None
    probability: float | None = None
    severity: ConjunctionSeverity
    screened_at: datetime | None = None
