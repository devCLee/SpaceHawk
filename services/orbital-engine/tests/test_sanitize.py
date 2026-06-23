"""LLM sanitizer (DECISION D6): allowlist / fail-closed boundary tests.

These prove the *only* data reaching the external LLM is the explicitly-curated,
anonymized subset built by :func:`to_llm_facts`. The critical test extends the
payload with a brand-new sensitive-looking field and asserts it cannot appear in
the serialized facts — because the sanitizer constructs ``LLMFacts`` from scratch
(allowlist), not by stripping known-bad keys (denylist).

Country codes/names (NK/CN/RU/JP + owner codes) are the PUBLIC subject of the
report and are intentionally ALLOWED through; only individual object identities
(satellites, conjunction objects, debris) are tokenized.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from orbital_engine.reports.sanitize import LLMFacts, SanitizeResult, to_llm_facts
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryActivity,
    DailyReportPayload,
    DebrisRiskCounts,
    HighRiskDebrisRow,
    SatellitePass,
    WatchlistRow,
)

REPORT_DATE = date(2026, 6, 20)
DAY_START = datetime(2026, 6, 20, tzinfo=UTC)

# Sensitive strings seeded into the payload; none may survive into the facts.
SENSITIVE_STRINGS = [
    "ISS (ZARYA)",  # satellite_name / conjunction primary_name
    "KEYHOLE 11",  # satellite_name / conjunction secondary_name
    "COSMOS DEB",  # debris_name
    "SH:CAT:000025544",  # raw satellite_id
    "1998-067A",  # raw satellite_id
    "관심위성 비고 메모",  # free-text remarks
]


def _populated_payload() -> DailyReportPayload:
    return DailyReportPayload(
        report_date=REPORT_DATE,
        watchlist_matrix=[
            WatchlistRow(
                country_code="PRK", country_name="북한", leo=3, meo=0, geo=0, heo=0, total=3
            ),
            WatchlistRow(
                country_code="PRC", country_name="중국", leo=10, meo=2, geo=4, heo=1, total=17
            ),
        ],
        watchlist_total=WatchlistRow(
            country_code="TOTAL", country_name=None, leo=13, meo=2, geo=4, heo=1, total=20
        ),
        country_activity=[
            CountryActivity(
                country_code="NK",
                country_name="북한",
                passes=[
                    SatellitePass(
                        satellite_name="ISS (ZARYA)",
                        satellite_id="SH:CAT:000025544",
                        pass_time=DAY_START + timedelta(hours=2),
                        closest_time=DAY_START + timedelta(hours=2, minutes=5),
                        closest_distance_km=512.3,
                        azimuth_deg=120.0,
                        elevation_deg=42.0,
                        remarks="관심위성 비고 메모",
                    )
                ],
            ),
            CountryActivity(country_code="CN", country_name="중국", passes=[]),
        ],
        conjunctions=[
            ConjunctionRow(
                satellite_name="ISS (ZARYA)",
                object_name="KEYHOLE 11",
                tca=DAY_START + timedelta(hours=12),
                distance_km=0.8,
                probability=1e-3,
                risk_category="HIGH",
            )
        ],
        debris_risk_counts=DebrisRiskCounts(critical=1, high=2, moderate=3, low=4),
        high_risk_debris=[
            HighRiskDebrisRow(
                country_code="PRC",
                country_name="중국",
                debris_name="COSMOS DEB",
                risk_grade="심각",
                rcs_size="LARGE",
                mean_altitude_km=780.0,
                period_min=100.5,
                perigee_km=760.0,
                apogee_km=800.0,
            )
        ],
    )


# --- Allowlisted key set (recursive) ---------------------------------------

_SAFE_KEYS = {
    "report_date",
    "watchlist",
    "watchlist_total",
    "country_activity",
    "conjunctions",
    "debris_risk_counts",
    "high_risk_debris",
    # watchlist leaf
    "country_code",
    "country_name",
    "leo",
    "meo",
    "geo",
    "heo",
    "total",
    # country_activity leaf
    "pass_count",
    "passes",
    "token",
    "closest_distance_km",
    "elevation_deg",
    # conjunction leaf
    "primary_token",
    "secondary_token",
    "distance_km",
    "probability",
    "tca",
    "risk_category",
    # debris counts leaf
    "critical",
    "high",
    "moderate",
    "low",
    # high-risk debris leaf
    "risk_grade",
    "rcs_size",
    "mean_altitude_km",
    "period_min",
    "perigee_km",
    "apogee_km",
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

    # §1 watchlist counts preserved verbatim (country IS allowed).
    assert {w.country_code: w.total for w in facts.watchlist} == {"PRK": 3, "PRC": 17}
    assert facts.watchlist[1].leo == 10
    assert facts.watchlist[1].geo == 4
    assert facts.watchlist_total is not None
    assert facts.watchlist_total.country_code == "TOTAL"
    assert facts.watchlist_total.total == 20

    # §2/§3 activity: pass_count + anonymized pass tokens with numeric fields.
    nk = facts.country_activity[0]
    assert nk.country_code == "NK"
    assert nk.country_name == "북한"
    assert nk.pass_count == 1
    assert nk.passes[0].closest_distance_km == 512.3
    assert nk.passes[0].elevation_deg == 42.0
    assert facts.country_activity[1].pass_count == 0

    # §4 distances / probability / dates / risk preserved.
    assert len(facts.conjunctions) == 1
    conj = facts.conjunctions[0]
    assert conj.distance_km == 0.8
    assert conj.probability == 1e-3
    assert conj.tca == DAY_START + timedelta(hours=12)
    assert conj.risk_category == "HIGH"

    # §5a counts preserved.
    assert facts.debris_risk_counts.critical == 1
    assert facts.debris_risk_counts.high == 2
    assert facts.debris_risk_counts.moderate == 3
    assert facts.debris_risk_counts.low == 4

    # §5c high-risk debris: numeric + risk + country preserved.
    d = facts.high_risk_debris[0]
    assert d.risk_grade == "심각"
    assert d.rcs_size == "LARGE"
    assert d.mean_altitude_km == 780.0
    assert d.perigee_km == 760.0
    assert d.apogee_km == 800.0
    assert d.country_code == "PRC"
    assert d.country_name == "중국"


# --- Country codes ARE allowed (public subject) -----------------------------


def test_country_codes_and_names_are_present() -> None:
    blob = to_llm_facts(_populated_payload()).facts.model_dump_json()
    # Report country codes + owner codes/names are the report's public subject.
    for allowed in ("NK", "CN", "PRK", "PRC", "TOTAL", "북한", "중국"):
        assert allowed in blob, f"allowed country token missing from facts: {allowed!r}"


# --- Fail-closed: a NEW sensitive field must NOT leak [CRITICAL] -------------


def test_fail_closed_new_sensitive_field_is_excluded() -> None:
    """Extend a payload model with a brand-new sensitive field and prove the
    allowlist sanitizer drops it (it is never referenced in to_llm_facts).
    """
    payload = _populated_payload()

    # Inject a NEW, never-allowlisted sensitive field onto real nested model
    # instances (a plain attribute the sanitizer would have to *opt in* to copy).
    payload.country_activity[0].passes[0].__dict__["classification_marking"] = "TS//SI"
    payload.high_risk_debris[0].__dict__["unit_name"] = "고급분석단"

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

    # The NK pass satellite is tokenized (by satellite_id).
    pass_token = facts.country_activity[0].passes[0].token
    assert pass_token == "OBJ-1"
    assert alias[pass_token] == "SH:CAT:000025544"

    # The same satellite name reused in a conjunction keeps... a distinct token,
    # because the pass keys on satellite_id and the conjunction keys on name.
    conj = facts.conjunctions[0]
    assert conj.primary_token.startswith("OBJ-")
    assert conj.secondary_token.startswith("OBJ-")
    assert alias[conj.primary_token] == "ISS (ZARYA)"
    assert alias[conj.secondary_token] == "KEYHOLE 11"

    # Debris identity tokenized too.
    debris_token = facts.high_risk_debris[0].token
    assert debris_token.startswith("OBJ-")
    assert alias[debris_token] == "COSMOS DEB"

    # All tokens are distinct OBJ-N values.
    all_tokens = {pass_token, conj.primary_token, conj.secondary_token, debris_token}
    assert len(all_tokens) == 4


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
    assert facts.watchlist == []
    assert facts.watchlist_total is None
    assert facts.country_activity == []
    assert facts.conjunctions == []
    assert facts.high_risk_debris == []
    # Default zeroed debris risk counts.
    assert facts.debris_risk_counts.critical == 0
    assert facts.debris_risk_counts.low == 0
    assert result.alias_map == {}
