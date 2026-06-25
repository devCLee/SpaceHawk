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
    watchlist (§1) ........... [{country_code, country_name, leo, meo, geo, heo,
                                total}]  (country IS allowed — public subject)
    watchlist_total (§1) ..... {country_code='TOTAL', leo, meo, geo, heo, total}
    country_activity (§2/§3) . [{country_code, country_name, pass_count,
                                passes:[{token, closest_distance_km,
                                elevation_deg}]}]  (satellite identity → token)
    conjunctions (§4) ........ [{primary_token, secondary_token, distance_km,
                                probability, tca, risk_category}]  (ids → tokens)
    debris_risk_counts (§5a) . {critical, high, moderate, low}
    high_risk_debris (§5c) ... [{token, risk_grade, rcs_size, mean_altitude_km,
                                period_min, perigee_km, apogee_km, country_code,
                                country_name}]  (debris identity → token)

COUNTRY IS ALLOWED. The four report countries (NK/CN/RU/JP) and the owner
country codes/names are the PUBLIC subject of the report, so they are copied
verbatim and never tokenized. Only individual OBJECT identities are anonymized.

EXCLUDED by construction (never copied across): satellite_name / object_name /
debris_name, raw satellite_id / NORAD ids, conjunction primary/secondary names,
free-text remarks, and any future field.

Anonymization
-------------

Every individual object identity (satellite, conjunction primary/secondary,
debris) is replaced by an opaque, stable token ("OBJ-1", "OBJ-2", ...). The
token -> original mapping is returned separately in
:attr:`SanitizeResult.alias_map` so the caller can de-anonymize the LLM's prose
afterwards. The LLM only ever sees tokens for objects; country stays in clear.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from orbital_engine.reports.schemas import DailyReportPayload


class _Anonymizer:
    """Stable object-identity -> opaque-token mapper.

    Re-requesting a key returns the same token, so an object that appears in
    both §2/§3 activity and a §4 conjunction keeps one stable token across the
    whole report. Only object identities are tokenized; country is never a key.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}
        self.alias_map: dict[str, str] = {}

    def token(self, original: str) -> str:
        if original in self._seen:
            return self._seen[original]
        token = f"OBJ-{len(self._seen) + 1}"
        self._seen[original] = token
        self.alias_map[token] = original
        return token


class LLMWatchlistRow(BaseModel):
    """§1 — one country's watchlist counts by regime (country IS allowed)."""

    country_code: str
    country_name: str | None = None
    leo: int
    meo: int
    geo: int
    heo: int
    total: int


class LLMPassFact(BaseModel):
    """§2/§3 — one peninsula pass; the satellite is an opaque token."""

    token: str
    closest_distance_km: float | None = None
    elevation_deg: float | None = None


class LLMCountryActivityFact(BaseModel):
    """§2/§3 — one report country's activity (country allowed, sats tokenized)."""

    country_code: str
    country_name: str
    pass_count: int
    passes: list[LLMPassFact] = Field(default_factory=list)


class LLMConjunctionFact(BaseModel):
    """§4 — one close approach; both objects are opaque tokens."""

    primary_token: str
    secondary_token: str
    distance_km: float
    probability: float | None = None
    tca: datetime
    risk_category: str


class LLMDebrisRiskCounts(BaseModel):
    """§5a — object counts per risk level (purely numeric)."""

    critical: int
    high: int
    moderate: int
    low: int


class LLMHighRiskDebrisFact(BaseModel):
    """§5c — one high-risk debris object; identity tokenized, country allowed."""

    token: str
    risk_grade: str
    rcs_size: str | float | None = None
    mean_altitude_km: float | None = None
    period_min: float | None = None
    perigee_km: float | None = None
    apogee_km: float | None = None
    country_code: str
    country_name: str | None = None


class LLMFacts(BaseModel):
    """The ONLY data structure that may be serialized into the LLM prompt.

    Built field-by-field from an allowlist (see module docstring): it carries
    counts, distances/altitudes in km, probabilities, dates, regime categories,
    risk tiers, country codes/names (allowed) and anonymized object tokens — and
    nothing else.
    """

    report_date: date
    watchlist: list[LLMWatchlistRow] = Field(default_factory=list)
    watchlist_total: LLMWatchlistRow | None = None
    country_activity: list[LLMCountryActivityFact] = Field(default_factory=list)
    conjunctions: list[LLMConjunctionFact] = Field(default_factory=list)
    debris_risk_counts: LLMDebrisRiskCounts = Field(
        default_factory=lambda: LLMDebrisRiskCounts(critical=0, high=0, moderate=0, low=0)
    )
    high_risk_debris: list[LLMHighRiskDebrisFact] = Field(default_factory=list)


class SanitizeResult(BaseModel):
    """The sanitized facts plus the token -> original map for de-anonymization."""

    facts: LLMFacts
    alias_map: dict[str, str] = Field(default_factory=dict)


def _watchlist_row(row: object) -> LLMWatchlistRow:
    """Copy the allowlisted watchlist fields off a payload ``WatchlistRow``."""
    return LLMWatchlistRow(
        country_code=row.country_code,  # type: ignore[attr-defined]
        country_name=row.country_name,  # type: ignore[attr-defined]
        leo=row.leo,  # type: ignore[attr-defined]
        meo=row.meo,  # type: ignore[attr-defined]
        geo=row.geo,  # type: ignore[attr-defined]
        heo=row.heo,  # type: ignore[attr-defined]
        total=row.total,  # type: ignore[attr-defined]
    )


def to_llm_facts(payload: DailyReportPayload) -> SanitizeResult:
    """Build the LLM-safe :class:`LLMFacts` from ``payload`` (allowlist).

    Each safe field is read explicitly off the payload and placed into a freshly
    constructed ``LLMFacts``; nothing is copied wholesale. Country codes/names
    are copied verbatim (allowed); individual object identities (satellites,
    conjunction objects, debris) become opaque ``OBJ-N`` tokens, with the
    token -> original mapping returned in :attr:`SanitizeResult.alias_map` for
    later de-anonymization of the prose.
    """
    anon = _Anonymizer()

    watchlist = [_watchlist_row(r) for r in payload.watchlist_matrix]
    watchlist_total = (
        _watchlist_row(payload.watchlist_total) if payload.watchlist_total is not None else None
    )

    country_activity = [
        LLMCountryActivityFact(
            country_code=ca.country_code,
            country_name=ca.country_name,
            pass_count=len(ca.passes),
            passes=[
                LLMPassFact(
                    token=anon.token(p.satellite_id),
                    closest_distance_km=p.closest_distance_km,
                    elevation_deg=p.elevation_deg,
                )
                for p in ca.passes
            ],
        )
        for ca in payload.country_activity
    ]

    conjunctions = [
        LLMConjunctionFact(
            primary_token=anon.token(c.satellite_name),
            secondary_token=anon.token(c.object_name),
            distance_km=c.distance_km,
            probability=c.probability,
            tca=c.tca,
            risk_category=c.risk_category,
        )
        for c in payload.conjunctions
    ]

    debris_risk_counts = LLMDebrisRiskCounts(
        critical=payload.debris_risk_counts.critical,
        high=payload.debris_risk_counts.high,
        moderate=payload.debris_risk_counts.moderate,
        low=payload.debris_risk_counts.low,
    )

    high_risk_debris = [
        LLMHighRiskDebrisFact(
            token=anon.token(d.debris_name),
            risk_grade=d.risk_grade,
            rcs_size=d.rcs_size,
            mean_altitude_km=d.mean_altitude_km,
            period_min=d.period_min,
            perigee_km=d.perigee_km,
            apogee_km=d.apogee_km,
            country_code=d.country_code,
            country_name=d.country_name,
        )
        for d in payload.high_risk_debris
    ]

    facts = LLMFacts(
        report_date=payload.report_date,
        watchlist=watchlist,
        watchlist_total=watchlist_total,
        country_activity=country_activity,
        conjunctions=conjunctions,
        debris_risk_counts=debris_risk_counts,
        high_risk_debris=high_risk_debris,
    )
    return SanitizeResult(facts=facts, alias_map=dict(anon.alias_map))
