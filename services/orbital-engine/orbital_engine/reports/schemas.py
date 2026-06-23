"""Typed payload for the daily space-situation report (일일 우주현황보고).

This is the deterministic data contract handed to the rest of the HWPX pipeline.
It carries *numbers only* — no prose. T2 derives a safe, LLM-facing subset from
it; T4 reads the raw time series to render charts; the template-fill step reads
the table rows verbatim. Every field is typed so the downstream tasks never have
to re-parse free-form data.

Payload -> report-section mapping
=================================

    DailyReportPayload
    ├─ report_date ............... 보고서 표지 / 머리글 (date stamp)
    │
    ├─ surveillance_categories ... §1 감시위성 활동 — 분류별 집계 표
    │     (SurveillanceCategoryCount: category, count)
    ├─ surveillance_objects ...... §1 감시위성 활동 — 주요 객체 표
    │     (SurveillanceObjectRow: id/name/owner/regime/type)
    │
    ├─ conjunctions .............. §2 근접(충돌) 위험 — CDM/스크리닝 표
    │     (ConjunctionRow: pair, miss_km, prob, TCA, alert level)
    │
    ├─ maneuvers ................. §3 기동 분석 — 객체별 기동 표
    │     (ManeuverEntry: id/name, status, classification, Δv, epoch)
    │     status == INSUFFICIENT_HISTORY => "정보 없음" (history < 4 epochs)
    │
    ├─ reentries ................. §4 재진입/추락 예측 — 표 (decay_date 기반)
    │     (ReentryEntry: object, predicted window)
    │
    ├─ country_breakdown ......... §5 국가/소유자별 분포 표
    │     (CountryBreakdownEntry: owner_code, owner_name, count)
    │
    └─ time_series ............... 차트용 원시 시계열 (T4 렌더)
          (TimeSeriesSeries[apogee/perigee per object over time])
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ManeuverDataStatus(StrEnum):
    """Whether an object had enough history to run maneuver analysis.

    ``PRESENT`` — at least ``maneuver_min_history_points`` (4) gp_history epochs,
    so detection ran (a maneuver may or may not have been flagged).
    ``INSUFFICIENT_HISTORY`` — fewer than 4 epochs; the §3 표 renders "정보 없음".
    """

    PRESENT = "PRESENT"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class SurveillanceCategoryCount(BaseModel):
    """One row of the §1 분류별 집계 표 (counts by functional category)."""

    category: str = Field(description="Functional category, e.g. recon / 통신 / 기술시험.")
    count: int = Field(ge=0)


class SurveillanceObjectRow(BaseModel):
    """One notable surveillance object in the §1 주요 객체 표."""

    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    owner_code: str | None = Field(default=None, description="Space-Track owner/country code.")
    owner_name: str | None = Field(default=None, description="Resolved owner name, if known.")
    regime: str | None = Field(default=None, description="Orbital regime: LEO / MEO / GEO / HEO.")
    object_type: str | None = None


class ConjunctionRow(BaseModel):
    """One close-approach (근접/충돌) record for the §2 표."""

    conjunction_id: str
    primary_object_id: str
    primary_name: str
    secondary_object_id: str
    secondary_name: str
    miss_distance_km: float
    probability: float | None = None
    tca: datetime = Field(description="Time of closest approach (UTC).")
    alert_level: str = Field(description="Severity tier: LOW / MOD / HIGH.")


class ManeuverEntry(BaseModel):
    """One object's maneuver-analysis result for the §3 표.

    When ``status`` is ``INSUFFICIENT_HISTORY`` the analysis fields are ``None``
    (the row renders "정보 없음"); otherwise they carry the most recent detected
    maneuver, or stay ``None`` if history was sufficient but nothing was flagged.
    """

    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    status: ManeuverDataStatus
    history_epochs: int = Field(ge=0, description="gp_history epoch count for this object.")
    classification: str | None = Field(default=None, description="Maneuver purpose class.")
    delta_v_m_s: float | None = Field(default=None, description="Total Δv magnitude [m/s].")
    delta_sma_km: float | None = Field(default=None, description="Semi-major-axis step [km].")
    epoch: datetime | None = Field(default=None, description="Post-maneuver epoch (UTC).")


class ReentryEntry(BaseModel):
    """One predicted re-entry / decay for the §4 표.

    Sourced from ``space_object.decay_date`` (the engine holds no separate decay
    table). ``predicted_window_start/end`` bracket the day-resolution prediction.
    """

    object_id: str
    norad_cat_id: int | None = None
    object_name: str
    owner_code: str | None = None
    predicted_window_start: datetime
    predicted_window_end: datetime


class CountryBreakdownEntry(BaseModel):
    """One owner/country bucket for the §5 분포 표."""

    owner_code: str = Field(description="Space-Track owner/country code, or 'UNKNOWN'.")
    owner_name: str | None = Field(default=None, description="Resolved owner name, if known.")
    count: int = Field(ge=0)


class TimeSeriesPoint(BaseModel):
    """One sample in a per-object altitude series (chart input)."""

    epoch: datetime
    apogee_km: float | None = None
    perigee_km: float | None = None


class TimeSeriesSeries(BaseModel):
    """A per-object apogee/perigee series over time (T4 renders the chart)."""

    object_id: str
    object_name: str
    points: list[TimeSeriesPoint] = Field(default_factory=list)


class DailyReportPayload(BaseModel):
    """The complete deterministic data set for one day's report.

    Every section is empty-capable: a day with no data yields a valid payload
    whose lists are empty, so the template fill never sees a missing field.
    """

    report_date: date
    surveillance_categories: list[SurveillanceCategoryCount] = Field(default_factory=list)
    surveillance_objects: list[SurveillanceObjectRow] = Field(default_factory=list)
    conjunctions: list[ConjunctionRow] = Field(default_factory=list)
    maneuvers: list[ManeuverEntry] = Field(default_factory=list)
    reentries: list[ReentryEntry] = Field(default_factory=list)
    country_breakdown: list[CountryBreakdownEntry] = Field(default_factory=list)
    time_series: list[TimeSeriesSeries] = Field(default_factory=list)
