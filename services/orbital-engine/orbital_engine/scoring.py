"""Composite threat scoring across analysis methods (mentoring item #11 / S2).

Combines the per-object outputs of the five analysis methods into one 0-100
threat index. Every formula is documented here and every response exposes the
per-method component scores *and* the weights, so any composite value can be
recomputed by hand (interpretability is a design requirement, like
``debris_risk``).

Per-method normalization into [0, 1]:

  * **conjunction** — collision probability on a log scale:
    ``clamp01((log10(Pc) + 7) / 4)`` so Pc 1e-7 -> 0.0, 1e-5 -> 0.5,
    1e-3 -> 1.0 (the conventional screening HIGH threshold). When no Pc is
    available the screened severity tier falls back to HIGH 1.0 / MOD 0.6 /
    LOW 0.3.
  * **maneuver** — detector confidence (already 0..1), clamped.
  * **rpo** — co-planarity score (already 0..1), clamped.
  * **anomaly** — baseline deviation ``clamp01(sigma / 6)``; a novel maneuver
    type floors the component at 0.8 (new behavior is inherently suspicious).
  * **debris** — ``risk_score / 100`` (the 0-100 debris index).

Composite = ``100 * sum(w_k * c_k) / sum(w_k)`` over the *present* components
only: a method with no signal in the window is missing (``None``) and
renormalizes the denominator — it is never treated as zero threat. Threat
levels reuse the debris bands (``debris_risk.risk_level``: 20/45/70 ->
Low/Medium/High/Critical) so the vocabulary is shared across the UI.

Known v1 limits: RPO / anomaly inputs come from alert rows keyed on
``created_at``, so a persistent threat older than the query window drops out of
those components (use ``GREATEST(created_at, updated_at)`` later if it bites).
"""

from __future__ import annotations

import math

#: Method weights, normalized (sum = 1.0). Analyst-tunable constants.
WEIGHTS: dict[str, float] = {
    "conjunction": 0.30,
    "maneuver": 0.25,
    "rpo": 0.20,
    "anomaly": 0.15,
    "debris": 0.10,
}

#: Log-scale anchors for Pc normalization (SSA screening convention).
PC_FLOOR = 1e-7
PC_CEIL = 1e-3

#: Severity fallback when a conjunction has no computable Pc.
SEVERITY_FALLBACK: dict[str, float] = {"HIGH": 1.0, "MOD": 0.6, "LOW": 0.3}

#: Sigma at which a baseline deviation saturates the anomaly component.
ANOMALY_SIGMA_SAT = 6.0

#: Minimum anomaly component when a never-before-seen maneuver type appears.
NOVEL_TYPE_FLOOR = 0.8

#: An object whose *only* signal is debris risk is scored only at/above this
#: risk_score — otherwise every tracked debris fragment becomes a "threat".
DEBRIS_STANDALONE_MIN = 45.0


def clamp01(value: float) -> float:
    """Clamp a value into [0, 1]."""
    return max(0.0, min(1.0, value))


def maneuver_component(max_confidence: float) -> float:
    """Detector confidence (0..1), clamped."""
    return clamp01(max_confidence)


def rpo_component(coplanarity: float) -> float:
    """Co-planarity score (0..1), clamped."""
    return clamp01(coplanarity)


def debris_component(risk_score: float) -> float:
    """Debris risk index (0..100) scaled to 0..1."""
    return clamp01(risk_score / 100.0)


def conjunction_component(max_pc: float | None, severity: str | None) -> float | None:
    """Log-scaled Pc, falling back to the severity tier when Pc is unusable."""
    if max_pc is not None and max_pc > 0.0:
        return clamp01((math.log10(max_pc) + 7.0) / 4.0)
    if severity is not None:
        return SEVERITY_FALLBACK.get(severity.upper())
    return None


def anomaly_component(delta_v_sigma: float, novel_type: bool) -> float:
    """Baseline-deviation sigma scaled to 0..1, floored on a novel type."""
    component = clamp01(delta_v_sigma / ANOMALY_SIGMA_SAT)
    if novel_type:
        component = max(component, NOVEL_TYPE_FLOOR)
    return component


def composite_score(
    components: dict[str, float | None],
    weights: dict[str, float] = WEIGHTS,
) -> float | None:
    """0-100 weighted composite over the present components (reweighted).

    Missing methods (absent key or ``None``) renormalize the denominator so a
    single-signal object is scored on that signal alone, never diluted by
    zero-filled absences. Returns ``None`` when no component is present.
    """
    present = {k: v for k, v in components.items() if v is not None and k in weights}
    if not present:
        return None
    total_weight = sum(weights[k] for k in present)
    weighted = sum(weights[k] * v for k, v in present.items())
    return round(100.0 * weighted / total_weight, 1)
