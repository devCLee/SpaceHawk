"""ConjunctionAlerter: emit on new/escalated, de-dup, trust-calibrated floor."""

from __future__ import annotations

from datetime import UTC, datetime

from orbital_engine.alerts import ConjunctionAlerter
from orbital_engine.config import Settings
from orbital_engine.domain.conjunction import (
    Conjunction,
    ConjunctionSeverity,
    ConjunctionSource,
)


def _conj(cid: str, severity: ConjunctionSeverity, *, miss: float = 0.5) -> Conjunction:
    return Conjunction(
        id=cid,
        source=ConjunctionSource.SCREENING,
        primary_object_id="SH:CAT:000025544",
        primary_norad_cat_id=25544,
        primary_name="SAT A",
        secondary_object_id="SH:CAT:000025545",
        secondary_norad_cat_id=25545,
        secondary_name="SAT B",
        tca=datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC),
        miss_distance_km=miss,
        severity=severity,
    )


def _alerter(min_severity: str = "MOD") -> ConjunctionAlerter:
    return ConjunctionAlerter(Settings(conjunction_alert_min_severity=min_severity))


def test_emits_alert_for_new_conjunction() -> None:
    alerts = _alerter().evaluate([_conj("c1", ConjunctionSeverity.HIGH)])
    assert len(alerts) == 1
    a = alerts[0]
    assert a["type"] == "conjunction"
    assert a["severity"] == "HIGH"
    assert a["conjunction_id"] == "c1"
    assert a["payload"]["miss_distance_km"] == 0.5


def test_does_not_reemit_unchanged_conjunction() -> None:
    alerter = _alerter()
    first = alerter.evaluate([_conj("c1", ConjunctionSeverity.HIGH)])
    second = alerter.evaluate([_conj("c1", ConjunctionSeverity.HIGH)])
    assert len(first) == 1
    assert second == []


def test_reemits_when_severity_escalates() -> None:
    alerter = _alerter()
    assert len(alerter.evaluate([_conj("c1", ConjunctionSeverity.MOD)])) == 1
    assert len(alerter.evaluate([_conj("c1", ConjunctionSeverity.HIGH)])) == 1
    # ...but does not re-emit once it has alerted at the higher tier.
    assert alerter.evaluate([_conj("c1", ConjunctionSeverity.HIGH)]) == []


def test_ignores_conjunctions_below_floor() -> None:
    assert _alerter("MOD").evaluate([_conj("c1", ConjunctionSeverity.LOW)]) == []


def test_floor_is_configurable() -> None:
    high_only = _alerter("HIGH")
    assert high_only.evaluate([_conj("c1", ConjunctionSeverity.MOD)]) == []
    assert len(high_only.evaluate([_conj("c2", ConjunctionSeverity.HIGH)])) == 1
