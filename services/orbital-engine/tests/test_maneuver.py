"""Maneuver detection: PREFIL, robust V-pattern flag, and the canonical record.

Pure-function tests (no DB): synthetic ``gp_history``-shaped rows drive the
detector over known drag/burn series so the threshold behaviour is asserted
deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbital_engine.config import Settings
from orbital_engine.domain.maneuver import make_maneuver_id, semimajor_axis_km
from orbital_engine.maneuver import detect_maneuvers, median_abs_deviation

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _row(i: int, sma: float, *, object_id: str = "SH:25544", name: str = "ISS", norad: int = 25544):
    """One element set ``i`` days after BASE with the given semi-major axis."""
    return {
        "object_id": object_id,
        "object_name": name,
        "norad_cat_id": norad,
        "epoch": BASE + timedelta(days=i),
        "semimajor_axis_km": sma,
        "eccentricity": 0.0006,
        "inclination": 51.6,
        "ra_of_asc_node": 32.0,
    }


def _drag(n: int, *, start: float = 6790.0, step: float = -0.1) -> list[dict]:
    """A smooth decaying series (natural drag): constant small negative SMA step."""
    return [_row(i, start + step * i) for i in range(n)]


def test_semimajor_axis_recovers_leo_band() -> None:
    # ISS mean motion ~15.5 rev/day -> a ~ 6790 km (R_earth + ~410 km).
    assert 6750.0 < semimajor_axis_km(15.50079139) < 6830.0


def test_median_abs_deviation_is_robust() -> None:
    assert median_abs_deviation([1.0, 1.0, 1.0, 9.0], 1.0) == 0.0
    assert median_abs_deviation([], 0.0) == 0.0


def test_pure_drag_yields_no_maneuver() -> None:
    # 20 steps of -0.1 km: span (1.9 km) clears PREFIL, but every step is below
    # the 0.5 km floor, so nothing is flagged.
    assert detect_maneuvers(_drag(20), Settings()) == []


def test_too_few_points_returns_empty() -> None:
    assert detect_maneuvers(_drag(3), Settings()) == []


def test_flat_span_below_floor_prefiltered() -> None:
    # Eight epochs spanning < 0.5 km total: PREFIL rejects before any statistics.
    rows = [_row(i, 6790.0 + 0.01 * i) for i in range(8)]
    assert detect_maneuvers(rows, Settings()) == []


def test_injected_burn_detected_once() -> None:
    # Drag, then a single +5 km step (orbit raise), then drag resumes.
    smas = [6790.0, 6789.9, 6789.8, 6794.8, 6794.7, 6794.6]
    rows = [_row(i, s) for i, s in enumerate(smas)]
    maneuvers = detect_maneuvers(rows, Settings())
    assert len(maneuvers) == 1
    m = maneuvers[0]
    assert m.delta_sma_km > 4.9
    assert m.epoch_before == BASE + timedelta(days=2)
    assert m.epoch_after == BASE + timedelta(days=3)
    assert m.epoch_before < m.detected_epoch < m.epoch_after
    assert m.detection_statistic >= Settings().maneuver_mad_k
    assert 0.0 <= m.confidence <= 1.0
    assert m.id == make_maneuver_id("SH:25544", m.epoch_after)
    assert m.object_name == "ISS" and m.norad_cat_id == 25544


def test_zscore_branch_when_baseline_has_spread() -> None:
    # Varied drag steps give MAD > 0, so the burn is flagged via the z-score path
    # (a finite statistic), not the noiseless-baseline saturation sentinel.
    smas = [6790.0, 6789.85, 6789.65, 6789.5, 6795.0, 6794.8, 6794.65]
    rows = [_row(i, s) for i, s in enumerate(smas)]
    maneuvers = detect_maneuvers(rows, Settings())
    assert len(maneuvers) == 1
    assert maneuvers[0].detection_statistic < 999.0


def test_unordered_history_is_sorted_before_detection() -> None:
    # fetch_history returns newest-first; detection must still bracket correctly.
    smas = [6790.0, 6789.9, 6789.8, 6794.8, 6794.7]
    rows = list(reversed([_row(i, s) for i, s in enumerate(smas)]))
    maneuvers = detect_maneuvers(rows, Settings())
    assert len(maneuvers) == 1
    assert maneuvers[0].epoch_before < maneuvers[0].epoch_after


def test_sma_recovered_from_mean_motion_when_column_null() -> None:
    # No semimajor_axis_km column: a mean-motion drop (orbit raise) is recovered.
    mms = [15.50, 15.50, 15.50, 15.30, 15.30]
    rows = []
    for i, mm in enumerate(mms):
        r = _row(i, 0.0)
        del r["semimajor_axis_km"]
        r["mean_motion"] = mm
        rows.append(r)
    maneuvers = detect_maneuvers(rows, Settings())
    assert len(maneuvers) == 1
    assert maneuvers[0].delta_sma_km > 0.5  # lower mean motion => higher orbit


def test_threshold_is_tunable() -> None:
    # A 0.6 km step clears the default floor but a raised floor suppresses it.
    smas = [6790.0, 6789.9, 6789.3, 6789.2, 6789.1]
    rows = [_row(i, s) for i, s in enumerate(smas)]
    assert len(detect_maneuvers(rows, Settings())) == 1
    assert detect_maneuvers(rows, Settings(maneuver_min_delta_sma_km=1.0)) == []
