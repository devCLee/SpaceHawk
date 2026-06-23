"""Allowlist sanitizer: derive the *only* data that may reach the external LLM.

DECISION D6 — ALLOWLIST, FAIL-CLOSED
====================================

The daily report later sends facts to a FREE external LLM API to write Korean
prose. The content is military-adjacent space-domain-awareness, so the prompt
must NEVER carry sensitive catalog text. This module enforces that by
*constructing a fresh, neutral object from scratch* (:class:`LLMFacts`) — it
explicitly reads each allowlisted field off the payload and copies it across.

This is the inverse of a denylist: we do NOT iterate the payload and strip
"bad" keys. Anything not named below is excluded *by construction*, so any new
field added to ``DailyReportPayload`` later cannot leak through this boundary
unless someone deliberately wires it into the allowlist here.

Allowlisted safe-field set (everything else is dropped)
------------------------------------------------------

    report_date .............. date
    §1 categories ............ {category, count}                (counts only)
    §1 objects ............... {token, regime, object_type}     (id anonymized)
    §2 conjunctions .......... {primary_token, secondary_token, miss_distance_km,
                                probability, tca, alert_level}  (ids anonymized)
    §3 maneuvers ............. {token, status, history_epochs, classification,
                                delta_v_m_s, delta_sma_km, epoch}  (id anonymized)
    §4 reentries ............. {token, predicted_window_start, predicted_window_end}
    §5 country_breakdown ..... {token, count}                   (owner anonymized)
    charts (time_series) ..... {token, points:[{epoch, apogee_km, perigee_km}]}

EXCLUDED by construction (never copied across): raw object_id / norad_cat_id,
object_name, owner_code, owner_name, primary_name / secondary_name, raw
conjunction_id, and any future field.

Anonymization
-------------

Every real identity (object_id / NORAD / name, owner code, conjunction id) is
replaced by an opaque, stable token ("OBJ-1", "OBJ-2", "OWN-1", "CDM-1", ...).
The token -> original mapping is returned separately in
:attr:`SanitizeResult.alias_map` so the caller can de-anonymize the LLM's prose
afterwards. The LLM only ever sees tokens.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from orbital_engine.reports.schemas import DailyReportPayload


class _Anonymizer:
    """Stable real-identity -> opaque-token mapper.

    Keys are namespaced by prefix so the same string used as both an object id
    and (hypothetically) an owner code never collides, and so tokens read
    meaningfully in the prose ("OBJ-1" vs "OWN-1"). Re-requesting a key returns
    the same token, so a satellite that appears in §1, §3 and the charts keeps
    one stable token across the whole report.
    """

    def __init__(self) -> None:
        self._by_prefix: dict[str, dict[str, str]] = {}
        self.alias_map: dict[str, str] = {}

    def token(self, prefix: str, original: str) -> str:
        seen = self._by_prefix.setdefault(prefix, {})
        if original in seen:
            return seen[original]
        token = f"{prefix}-{len(seen) + 1}"
        seen[original] = token
        self.alias_map[token] = original
        return token


class LLMCategoryFact(BaseModel):
    """§1 — one functional-category count (no object identity)."""

    category: str
    count: int


class LLMObjectFact(BaseModel):
    """§1 — one notable object, identity reduced to an opaque token."""

    token: str
    regime: str | None = None
    object_type: str | None = None


class LLMConjunctionFact(BaseModel):
    """§2 — one close approach; both objects are opaque tokens."""

    primary_token: str
    secondary_token: str
    miss_distance_km: float
    probability: float | None = None
    tca: datetime
    alert_level: str


class LLMManeuverFact(BaseModel):
    """§3 — one maneuver-analysis result, identity reduced to a token."""

    token: str
    status: str
    history_epochs: int
    classification: str | None = None
    delta_v_m_s: float | None = None
    delta_sma_km: float | None = None
    epoch: datetime | None = None


class LLMReentryFact(BaseModel):
    """§4 — one predicted re-entry, identity reduced to a token."""

    token: str
    predicted_window_start: datetime
    predicted_window_end: datetime


class LLMCountryFact(BaseModel):
    """§5 — one owner/country bucket; the owner is an opaque token."""

    token: str
    count: int


class LLMTimeSeriesPoint(BaseModel):
    """One altitude sample (purely numeric)."""

    epoch: datetime
    apogee_km: float | None = None
    perigee_km: float | None = None


class LLMTimeSeriesFact(BaseModel):
    """One per-object altitude series, identity reduced to a token."""

    token: str
    points: list[LLMTimeSeriesPoint] = Field(default_factory=list)


class LLMFacts(BaseModel):
    """The ONLY data structure that may be serialized into the LLM prompt.

    Built field-by-field from an allowlist (see module docstring): it carries
    counts, distances/altitudes in km, probabilities, dates, regime/type
    categories, status enums and anonymized tokens — and nothing else.
    """

    report_date: date
    categories: list[LLMCategoryFact] = Field(default_factory=list)
    objects: list[LLMObjectFact] = Field(default_factory=list)
    conjunctions: list[LLMConjunctionFact] = Field(default_factory=list)
    maneuvers: list[LLMManeuverFact] = Field(default_factory=list)
    reentries: list[LLMReentryFact] = Field(default_factory=list)
    country_breakdown: list[LLMCountryFact] = Field(default_factory=list)
    time_series: list[LLMTimeSeriesFact] = Field(default_factory=list)


class SanitizeResult(BaseModel):
    """The sanitized facts plus the token -> original map for de-anonymization."""

    facts: LLMFacts
    alias_map: dict[str, str] = Field(default_factory=dict)


def to_llm_facts(payload: DailyReportPayload) -> SanitizeResult:
    """Build the LLM-safe :class:`LLMFacts` from ``payload`` (allowlist).

    Each safe field is read explicitly off the payload and placed into a freshly
    constructed ``LLMFacts``; nothing is copied wholesale. Real identities become
    opaque tokens, with the token -> original mapping returned in
    :attr:`SanitizeResult.alias_map` for later de-anonymization of the prose.
    """
    anon = _Anonymizer()

    categories = [
        LLMCategoryFact(category=c.category, count=c.count)
        for c in payload.surveillance_categories
    ]

    objects = [
        LLMObjectFact(
            token=anon.token("OBJ", o.object_id),
            regime=o.regime,
            object_type=o.object_type,
        )
        for o in payload.surveillance_objects
    ]

    conjunctions = [
        LLMConjunctionFact(
            primary_token=anon.token("OBJ", c.primary_object_id),
            secondary_token=anon.token("OBJ", c.secondary_object_id),
            miss_distance_km=c.miss_distance_km,
            probability=c.probability,
            tca=c.tca,
            alert_level=c.alert_level,
        )
        for c in payload.conjunctions
    ]

    maneuvers = [
        LLMManeuverFact(
            token=anon.token("OBJ", m.object_id),
            status=m.status.value,
            history_epochs=m.history_epochs,
            classification=m.classification,
            delta_v_m_s=m.delta_v_m_s,
            delta_sma_km=m.delta_sma_km,
            epoch=m.epoch,
        )
        for m in payload.maneuvers
    ]

    reentries = [
        LLMReentryFact(
            token=anon.token("OBJ", r.object_id),
            predicted_window_start=r.predicted_window_start,
            predicted_window_end=r.predicted_window_end,
        )
        for r in payload.reentries
    ]

    country_breakdown = [
        LLMCountryFact(token=anon.token("OWN", c.owner_code), count=c.count)
        for c in payload.country_breakdown
    ]

    time_series = [
        LLMTimeSeriesFact(
            token=anon.token("OBJ", s.object_id),
            points=[
                LLMTimeSeriesPoint(
                    epoch=p.epoch, apogee_km=p.apogee_km, perigee_km=p.perigee_km
                )
                for p in s.points
            ],
        )
        for s in payload.time_series
    ]

    facts = LLMFacts(
        report_date=payload.report_date,
        categories=categories,
        objects=objects,
        conjunctions=conjunctions,
        maneuvers=maneuvers,
        reentries=reentries,
        country_breakdown=country_breakdown,
        time_series=time_series,
    )
    return SanitizeResult(facts=facts, alias_map=dict(anon.alias_map))
