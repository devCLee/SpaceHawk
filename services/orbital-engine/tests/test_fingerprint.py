"""Behavioral baselines + deviation scoring (feature #14, the innovation spine).

Pure-function tests: synthetic maneuver histories drive baseline construction and
the Δv / novel-class deviation flagging deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbital_engine.alerts import AnomalyMonitor
from orbital_engine.config import Settings
from orbital_engine.domain.maneuver import Maneuver, ManeuverType
from orbital_engine.fingerprint import build_baseline, score_deviation

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _mv(i: int, *, dv: float, mtype: ManeuverType = ManeuverType.STATION_KEEPING) -> Maneuver:
    """A maneuver ``i`` periods in, with the given Δv and purpose class."""
    return Maneuver(
        id=f"MNV:SH:23:{i}",
        object_id="SH:23",
        object_name="SJ-23",
        epoch_before=BASE + timedelta(days=30 * i),
        epoch_after=BASE + timedelta(days=30 * i, hours=1),
        detected_epoch=BASE + timedelta(days=30 * i),
        delta_sma_km=1.0,
        delta_ecc=0.0,
        delta_inc_deg=0.0,
        delta_raan_deg=0.0,
        detection_statistic=50.0,
        confidence=1.0,
        delta_v_m_s=dv,
        maneuver_type=mtype,
    )


def test_too_few_maneuvers_no_baseline() -> None:
    assert build_baseline([_mv(0, dv=5.0), _mv(1, dv=5.0)], Settings()) is None


def test_baseline_summarizes_cadence_and_dv() -> None:
    # Monthly station-keeping at ~5 m/s.
    history = [_mv(i, dv=5.0 + (i % 2) * 0.2) for i in range(6)]
    b = build_baseline(history, Settings())
    assert b is not None
    assert b.sample_count == 6
    assert 4.9 < b.mean_delta_v_m_s < 5.3
    assert abs(b.mean_interval_days - 30.0) < 0.5
    assert b.type_distribution == {"STATION_KEEPING": 6}
    assert b.object_name == "SJ-23"


def test_routine_maneuver_not_anomalous() -> None:
    history = [_mv(i, dv=5.0) for i in range(5)]
    b = build_baseline(history, Settings())
    assert b is not None
    dev = score_deviation(b, _mv(5, dv=5.1), Settings())
    assert not dev.is_anomalous
    assert not dev.novel_type


def test_large_dv_jump_is_anomalous() -> None:
    # Baseline ~5 m/s with small spread; a 60 m/s burn is many σ out.
    history = [_mv(i, dv=5.0 + (i % 3) * 0.3) for i in range(6)]
    b = build_baseline(history, Settings())
    assert b is not None
    dev = score_deviation(b, _mv(6, dv=60.0), Settings())
    assert dev.is_anomalous
    assert dev.delta_v_sigma >= Settings().fingerprint_deviation_sigma
    assert any("σ" in r for r in dev.reasons)


def test_novel_purpose_class_is_anomalous() -> None:
    history = [_mv(i, dv=5.0) for i in range(5)]
    b = build_baseline(history, Settings())
    assert b is not None
    # Same Δv magnitude, but a class this object has never performed.
    dev = score_deviation(b, _mv(5, dv=5.0, mtype=ManeuverType.RPO), Settings())
    assert dev.is_anomalous
    assert dev.novel_type


def test_uniform_baseline_uses_relative_fallback() -> None:
    # Zero Δv spread (MAD==0): a modest jump still trips the relative fallback,
    # a near-identical Δv does not (no infinite sensitivity).
    history = [_mv(i, dv=10.0) for i in range(5)]
    b = build_baseline(history, Settings())
    assert b is not None and b.delta_v_mad_m_s == 0.0
    assert not score_deviation(b, _mv(5, dv=10.2), Settings()).is_anomalous
    assert score_deviation(b, _mv(5, dv=40.0), Settings()).is_anomalous


def test_anomaly_monitor_emits_once_per_maneuver() -> None:
    history = [_mv(i, dv=5.0) for i in range(5)]
    b = build_baseline(history, Settings())
    assert b is not None
    burn = _mv(5, dv=80.0)
    dev = score_deviation(b, burn, Settings())
    monitor = AnomalyMonitor(Settings())
    first = monitor.evaluate([(dev, burn)])
    assert len(first) == 1
    a = first[0]
    assert a["type"] == "maneuver-anomaly" and a["severity"] == "HIGH"
    assert a["id"] == "ANOM:MNV:SH:23:5" and a["object_id"] == "SH:23"
    # Same anomaly again => not re-emitted.
    assert monitor.evaluate([(dev, burn)]) == []
