"""Composite threat scoring (mentoring item #11 / S2).

Pure-function tests: per-method normalization into [0, 1], the documented
weighted composite with missing-method reweighting, and the shared threat-level
bands. No DB.
"""

from __future__ import annotations

import math

from orbital_engine.debris_risk import risk_level
from orbital_engine.scoring import (
    WEIGHTS,
    anomaly_component,
    composite_score,
    conjunction_component,
    debris_component,
    maneuver_component,
    rpo_component,
)


def test_weights_sum_to_one() -> None:
    assert math.isclose(sum(WEIGHTS.values()), 1.0)
    assert set(WEIGHTS) == {"conjunction", "maneuver", "rpo", "anomaly", "debris"}


def test_identity_components_clamp() -> None:
    assert maneuver_component(0.7) == 0.7
    assert maneuver_component(1.5) == 1.0
    assert maneuver_component(-0.1) == 0.0
    assert rpo_component(0.4) == 0.4
    assert rpo_component(2.0) == 1.0
    assert debris_component(45.0) == 0.45
    assert debris_component(250.0) == 1.0


def test_conjunction_component_log_scales_pc() -> None:
    assert conjunction_component(1e-3, None) == 1.0
    assert math.isclose(conjunction_component(1e-5, None), 0.5)
    assert conjunction_component(1e-7, None) == 0.0
    assert conjunction_component(1e-2, None) == 1.0  # above ceiling clamps
    assert conjunction_component(1e-9, None) == 0.0  # below floor clamps


def test_conjunction_component_severity_fallback() -> None:
    # No usable Pc (None or 0): fall back to the screened severity tier.
    assert conjunction_component(None, "HIGH") == 1.0
    assert conjunction_component(0.0, "MOD") == 0.6
    assert conjunction_component(None, "LOW") == 0.3
    assert conjunction_component(None, None) is None


def test_anomaly_component_sigma_and_novel_type() -> None:
    assert math.isclose(anomaly_component(3.0, False), 0.5)
    assert anomaly_component(6.0, False) == 1.0
    assert anomaly_component(12.0, False) == 1.0  # saturates
    assert anomaly_component(0.0, True) == 0.8  # novel-type floor
    assert anomaly_component(6.0, True) == 1.0  # floor never lowers


def test_composite_all_components_is_weighted_sum() -> None:
    components = {
        "conjunction": 1.0,
        "maneuver": 0.5,
        "rpo": 0.0,
        "anomaly": 1.0,
        "debris": 0.5,
    }
    expected = 100.0 * (0.30 * 1.0 + 0.25 * 0.5 + 0.20 * 0.0 + 0.15 * 1.0 + 0.10 * 0.5)
    assert composite_score(components) == round(expected, 1)


def test_composite_reweights_missing_methods() -> None:
    # A single present component c scores 100*c regardless of its weight:
    # missing methods renormalize the denominator, they are never zero-filled.
    assert composite_score({"rpo": 0.6}) == 60.0
    assert composite_score({"debris": 0.45, "maneuver": None}) == 45.0
    # Two present components: weighted mean over their own weights only.
    two = composite_score({"conjunction": 1.0, "maneuver": 0.0})
    assert two == round(100.0 * 0.30 / (0.30 + 0.25), 1)


def test_composite_empty_is_none() -> None:
    assert composite_score({}) is None
    assert composite_score({"maneuver": None, "rpo": None}) is None


def test_threat_level_reuses_debris_bands() -> None:
    assert risk_level(19.9) == "Low"
    assert risk_level(20.0) == "Medium"
    assert risk_level(44.9) == "Medium"
    assert risk_level(45.0) == "High"
    assert risk_level(69.9) == "High"
    assert risk_level(70.0) == "Critical"
