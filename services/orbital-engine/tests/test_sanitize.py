"""LLM sanitizer (DECISION D6): allowlist / fail-closed boundary tests.

These prove the *only* data reaching the external LLM is the explicitly-curated,
anonymized subset built by :func:`to_llm_facts`. The critical test extends the
payload with a brand-new sensitive-looking field and asserts it cannot appear in
the serialized facts — because the sanitizer constructs ``LLMFacts`` from scratch
(allowlist), not by stripping known-bad keys (denylist).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from orbital_engine.reports.sanitize import LLMFacts, SanitizeResult, to_llm_facts
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryBreakdownEntry,
    DailyReportPayload,
    ManeuverDataStatus,
    ManeuverEntry,
    ReentryEntry,
    SurveillanceCategoryCount,
    SurveillanceObjectRow,
    TimeSeriesPoint,
    TimeSeriesSeries,
)

REPORT_DATE = date(2026, 6, 20)
DAY_START = datetime(2026, 6, 20, tzinfo=UTC)

# Sensitive strings seeded into the payload; none may survive into the facts.
SENSITIVE_STRINGS = [
    "ISS (ZARYA)",  # object_name
    "KEYHOLE 11",  # object_name
    "US",  # owner_code
    "PRC",  # owner_code
    "미국",  # owner_name
    "중국",  # owner_name
    "SH:CAT:000025544",  # raw object_id
    "1998-067A",  # raw object_id
    "SCR:A:B:20260620T1200",  # raw conjunction_id
]


def _populated_payload() -> DailyReportPayload:
    oid_a = "SH:CAT:000025544"
    oid_b = "1998-067A"
    return DailyReportPayload(
        report_date=REPORT_DATE,
        surveillance_categories=[
            SurveillanceCategoryCount(category="위성(탑재체)", count=2),
            SurveillanceCategoryCount(category="파편", count=1),
        ],
        surveillance_objects=[
            SurveillanceObjectRow(
                object_id=oid_a,
                norad_cat_id=25544,
                object_name="ISS (ZARYA)",
                owner_code="US",
                owner_name="미국",
                regime="LEO",
                object_type="PAYLOAD",
            ),
            SurveillanceObjectRow(
                object_id=oid_b,
                norad_cat_id=11111,
                object_name="KEYHOLE 11",
                owner_code="US",
                owner_name="미국",
                regime="LEO",
                object_type="PAYLOAD",
            ),
        ],
        conjunctions=[
            ConjunctionRow(
                conjunction_id="SCR:A:B:20260620T1200",
                primary_object_id=oid_a,
                primary_name="ISS (ZARYA)",
                secondary_object_id=oid_b,
                secondary_name="KEYHOLE 11",
                miss_distance_km=0.8,
                probability=1e-3,
                tca=DAY_START + timedelta(hours=12),
                alert_level="HIGH",
            )
        ],
        maneuvers=[
            ManeuverEntry(
                object_id=oid_a,
                norad_cat_id=25544,
                object_name="ISS (ZARYA)",
                status=ManeuverDataStatus.PRESENT,
                history_epochs=5,
                classification="STATIONKEEP",
                delta_v_m_s=1.4,
                delta_sma_km=5.0,
                epoch=DAY_START + timedelta(hours=3),
            )
        ],
        reentries=[
            ReentryEntry(
                object_id=oid_b,
                norad_cat_id=11111,
                object_name="KEYHOLE 11",
                owner_code="PRC",
                predicted_window_start=DAY_START,
                predicted_window_end=DAY_START + timedelta(days=1),
            )
        ],
        country_breakdown=[
            CountryBreakdownEntry(owner_code="US", owner_name="미국", count=2),
            CountryBreakdownEntry(owner_code="PRC", owner_name="중국", count=1),
        ],
        time_series=[
            TimeSeriesSeries(
                object_id=oid_a,
                object_name="ISS (ZARYA)",
                points=[
                    TimeSeriesPoint(epoch=DAY_START, apogee_km=420.0, perigee_km=410.0),
                    TimeSeriesPoint(
                        epoch=DAY_START + timedelta(hours=1), apogee_km=421.0, perigee_km=411.0
                    ),
                ],
            )
        ],
    )


# --- Allowlisted key set (recursive) ---------------------------------------

_SAFE_KEYS = {
    "report_date",
    "categories",
    "objects",
    "conjunctions",
    "maneuvers",
    "reentries",
    "country_breakdown",
    "time_series",
    # leaf facts
    "category",
    "count",
    "token",
    "regime",
    "object_type",
    "primary_token",
    "secondary_token",
    "miss_distance_km",
    "probability",
    "tca",
    "alert_level",
    "status",
    "history_epochs",
    "classification",
    "delta_v_m_s",
    "delta_sma_km",
    "epoch",
    "predicted_window_start",
    "predicted_window_end",
    "points",
    "apogee_km",
    "perigee_km",
}


def _all_keys(obj: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


# --- Happy path -------------------------------------------------------------


def test_happy_path_preserves_safe_fields() -> None:
    result = to_llm_facts(_populated_payload())
    facts = result.facts

    assert isinstance(result, SanitizeResult)
    assert isinstance(facts, LLMFacts)
    assert facts.report_date == REPORT_DATE

    # §1 counts preserved verbatim.
    assert {c.category: c.count for c in facts.categories} == {"위성(탑재체)": 2, "파편": 1}
    assert len(facts.objects) == 2
    assert facts.objects[0].regime == "LEO"
    assert facts.objects[0].object_type == "PAYLOAD"

    # §2 distances / probability / dates preserved.
    assert len(facts.conjunctions) == 1
    conj = facts.conjunctions[0]
    assert conj.miss_distance_km == 0.8
    assert conj.probability == 1e-3
    assert conj.tca == DAY_START + timedelta(hours=12)
    assert conj.alert_level == "HIGH"

    # §3 maneuver magnitudes / status preserved.
    mnv = facts.maneuvers[0]
    assert mnv.status == "PRESENT"
    assert mnv.history_epochs == 5
    assert mnv.delta_v_m_s == 1.4
    assert mnv.delta_sma_km == 5.0
    assert mnv.classification == "STATIONKEEP"

    # §4 window dates preserved.
    assert facts.reentries[0].predicted_window_start == DAY_START
    assert facts.reentries[0].predicted_window_end == DAY_START + timedelta(days=1)

    # §5 counts preserved.
    assert sorted(c.count for c in facts.country_breakdown) == [1, 2]

    # charts: numeric points preserved.
    assert len(facts.time_series[0].points) == 2
    assert facts.time_series[0].points[0].apogee_km == 420.0


# --- Fail-closed: a NEW sensitive field must NOT leak [CRITICAL] -------------


def test_fail_closed_new_sensitive_field_is_excluded() -> None:
    """Extend a payload model with a brand-new sensitive field and prove the
    allowlist sanitizer drops it (it is never referenced in to_llm_facts).
    """
    payload = _populated_payload()

    # Inject a NEW, never-allowlisted sensitive field onto a real nested model
    # instance (pydantic v2 keeps __pydantic_extra__-style attrs accessible; we
    # set a plain attribute the sanitizer would have to *opt in* to copy).
    payload.surveillance_objects[0].__dict__["classification_marking"] = "TS//SI"
    payload.surveillance_objects[0].__dict__["unit_name"] = "고급분석단"

    result = to_llm_facts(payload)
    dumped = result.facts.model_dump()

    # Allowlist proof: every key in the serialized facts is in the known-safe set.
    assert _all_keys(dumped) <= _SAFE_KEYS

    # And the injected fields appear nowhere in the serialized JSON.
    blob = json.dumps(dumped, default=str)
    assert "classification_marking" not in blob
    assert "TS//SI" not in blob
    assert "unit_name" not in blob
    assert "고급분석단" not in blob


def test_serialized_keys_are_subset_of_safe_set() -> None:
    dumped = to_llm_facts(_populated_payload()).facts.model_dump()
    assert _all_keys(dumped) <= _SAFE_KEYS


# --- Anonymization round-trip -----------------------------------------------


def test_identities_anonymized_and_alias_map_round_trips() -> None:
    result = to_llm_facts(_populated_payload())
    facts = result.facts
    alias = result.alias_map

    # Objects carry opaque tokens, not raw ids.
    tokens = {o.token for o in facts.objects}
    assert tokens == {"OBJ-1", "OBJ-2"}

    # The same object id keeps one stable token across §1 / §3 / §2 / charts.
    obj_a_token = facts.objects[0].token
    assert facts.maneuvers[0].token == obj_a_token
    assert facts.conjunctions[0].primary_token == obj_a_token
    assert facts.time_series[0].token == obj_a_token

    # Owner codes anonymized under their own namespace.
    owner_tokens = {c.token for c in facts.country_breakdown}
    assert owner_tokens == {"OWN-1", "OWN-2"}

    # alias_map round-trips token -> original (de-anonymization of LLM prose).
    assert alias[obj_a_token] == "SH:CAT:000025544"
    assert alias[facts.objects[1].token] == "1998-067A"
    assert {alias[t] for t in owner_tokens} == {"US", "PRC"}


# --- No-leak string scan ----------------------------------------------------


def test_no_sensitive_string_in_serialized_facts() -> None:
    result = to_llm_facts(_populated_payload())
    blob = result.facts.model_dump_json()
    for sensitive in SENSITIVE_STRINGS:
        assert sensitive not in blob, f"sensitive string leaked into facts: {sensitive!r}"


# --- Empty payload ----------------------------------------------------------


def test_empty_payload_yields_valid_empty_facts() -> None:
    payload = DailyReportPayload(report_date=REPORT_DATE)
    result = to_llm_facts(payload)
    facts = result.facts
    assert isinstance(facts, LLMFacts)
    assert facts.report_date == REPORT_DATE
    assert facts.categories == []
    assert facts.objects == []
    assert facts.conjunctions == []
    assert facts.maneuvers == []
    assert facts.reentries == []
    assert facts.country_breakdown == []
    assert facts.time_series == []
    assert result.alias_map == {}
