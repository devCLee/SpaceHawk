"""Typed payload for the daily space-operations report (일일 우주작전현황 보고).

The deterministic data contract handed to the rest of the HWPX pipeline. It
carries *numbers only* — no LLM prose, no image bytes (those ride in the sibling
:class:`ReportProse` and :class:`ReportImages` contracts). Satellite passes are
computed engine-side (R2); the watchlist matrix is the whole catalog grouped by
country × regime; the globe + debris images are supplied by the web layer.

Model -> report-section mapping
===============================

    §1  관심목록 등록 위성 현황 ............ DailyReportPayload.watchlist_matrix
                                            (WatchlistRow + watchlist_total)
    §2  북한 위성 활동 현황 ................ DailyReportPayload.country_activity[NK]
                                            (CountryActivity / SatellitePass)
                                            + ReportImages.country_globes["NK"]
    §3  주변국 위성 활동 현황 .............. DailyReportPayload.country_activity[CN/RU/JP]
                                            (CountryActivity / SatellitePass)
                                            + ReportImages.country_globes[CN/RU/JP]
    §4  근접 및 충돌 현황 ................. DailyReportPayload.conjunctions
                                            (ConjunctionRow)
    §5a 충돌 위험도 ...................... DailyReportPayload.debris_risk_counts
                                            (DebrisRiskCounts)
    §5b 고도별 잔해 밀도 + 히트맵 .......... ReportImages.debris_density
                                            + ReportImages.debris_heatmap
    §5c 고위험 잔해 현황 .................. DailyReportPayload.high_risk_debris
                                            (HighRiskDebrisRow)
    §6  일일 분석 내용 ................... ReportProse.analysis_items
                                            (AnalysisItem: detail + cause_forecast)
    §7  대응 작전 추진 내용 ............... ReportProse.response_ops
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReportCountry(StrEnum):
    """The four countries the report tracks (§2 북한, §3 주변국 중/러/일)."""

    NORTH_KOREA = "NK"
    CHINA = "CN"
    RUSSIA = "RU"
    JAPAN = "JP"


# --- §1 관심목록 등록 위성 현황 ------------------------------------------------


class WatchlistRow(BaseModel):
    """One country's watchlist counts by orbital regime, plus the row total.

    ``total`` is carried explicitly (not derived) so the table renders verbatim;
    the grand-total across countries lives in ``DailyReportPayload.watchlist_total``
    as a row whose ``country_code`` is ``"TOTAL"``.
    """

    country_code: str = Field(description="Space-Track owner/country code, or 'TOTAL'.")
    country_name: str | None = Field(default=None, description="Resolved country name, if known.")
    leo: int = Field(ge=0, description="Low Earth orbit count.")
    meo: int = Field(ge=0, description="Medium Earth orbit count.")
    geo: int = Field(ge=0, description="Geosynchronous orbit count.")
    heo: int = Field(ge=0, description="Highly elliptical orbit count.")
    total: int = Field(ge=0, description="Row total (leo + meo + geo + heo).")


# --- §2 / §3 위성 활동 현황 (한반도 통과) --------------------------------------


class SatellitePass(BaseModel):
    """One peninsula pass (한반도 통과) of a tracked satellite (R2 output).

    Closest-approach values are relative to 대전 KARI. All approach fields are
    optional so a pass with no computed closest point still renders.
    """

    satellite_name: str
    satellite_id: str = Field(description="USOID or NORAD id of the passing object.")
    pass_time: datetime = Field(description="Pass time over the peninsula (UTC).")
    closest_time: datetime | None = Field(default=None, description="Closest-approach time (UTC).")
    closest_distance_km: float | None = Field(
        default=None, description="Closest distance to 대전 KARI [km]."
    )
    azimuth_deg: float | None = Field(default=None, description="Azimuth at closest approach [deg].")
    elevation_deg: float | None = Field(
        default=None, description="Elevation at closest approach [deg]."
    )
    remarks: str | None = Field(default=None, description="Free-text note (비고).")


class CountryActivity(BaseModel):
    """All peninsula passes for one report country (§2 북한, §3 중/러/일)."""

    country_code: str = Field(description="Report-country code (NK / CN / RU / JP).")
    country_name: str
    passes: list[SatellitePass] = Field(default_factory=list)


# --- §4 근접 및 충돌 현황 ------------------------------------------------------


class ConjunctionRow(BaseModel):
    """One proximity / collision record for the §4 표."""

    satellite_name: str
    object_name: str = Field(description="Name of the close-approach / collision object.")
    tca: datetime = Field(description="Time of closest approach (최근접 시각, UTC).")
    distance_km: float = Field(description="Miss distance at TCA (최근접 거리) [km].")
    probability: float | None = Field(default=None, description="Collision probability (충돌 확률).")
    risk_category: str = Field(description="Risk tier (위험 구분).")


# --- §5 한반도 근처 우주 잔해 현황 --------------------------------------------


class DebrisRiskCounts(BaseModel):
    """§5a 충돌 위험도 — object counts per risk level.

    Maps debris_risk.RISK_LEVELS / risk_level(): Critical->심각, High->높음,
    Medium->보통, Low->낮음.
    """

    critical: int = Field(ge=0, description="심각 (Critical).")
    high: int = Field(ge=0, description="높음 (High).")
    moderate: int = Field(ge=0, description="보통 (Medium).")
    low: int = Field(ge=0, description="낮음 (Low).")


class HighRiskDebrisRow(BaseModel):
    """§5c 고위험 잔해 현황 — one high-risk debris object.

    ``rcs_size`` mirrors SpaceObject.rcs_size (RcsSize: SMALL/MEDIUM/LARGE) but
    accepts a numeric area too. Apsides map to SpaceObject.periapsis_km /
    apoapsis_km, ``period_min`` to period_min, ``mean_altitude_km`` to the
    computed shell altitude used by debris_risk.
    """

    country_code: str = Field(description="Space-Track owner/country code.")
    country_name: str | None = Field(default=None, description="Resolved country name, if known.")
    debris_name: str
    risk_grade: str = Field(description="Risk level (위험등급): 심각/높음/보통/낮음.")
    rcs_size: str | float | None = Field(
        default=None, description="RCS size class (SMALL/MEDIUM/LARGE) or area [m^2]."
    )
    mean_altitude_km: float | None = Field(default=None, description="Mean altitude [km].")
    period_min: float | None = Field(default=None, description="Orbital period [min].")
    perigee_km: float | None = Field(default=None, description="Perigee altitude [km].")
    apogee_km: float | None = Field(default=None, description="Apogee altitude [km].")


# --- Top-level deterministic payload ------------------------------------------


class DailyReportPayload(BaseModel):
    """The complete deterministic data set for one day's report (data only).

    Every section is empty-capable: a day with no data yields a valid payload
    whose lists are empty, so the template fill never sees a missing field.
    """

    report_date: date
    watchlist_matrix: list[WatchlistRow] = Field(default_factory=list)
    watchlist_total: WatchlistRow | None = Field(
        default=None, description="Grand-total row (country_code='TOTAL') across all countries."
    )
    country_activity: list[CountryActivity] = Field(default_factory=list)
    conjunctions: list[ConjunctionRow] = Field(default_factory=list)
    debris_risk_counts: DebrisRiskCounts = Field(
        default_factory=lambda: DebrisRiskCounts(critical=0, high=0, moderate=0, low=0)
    )
    high_risk_debris: list[HighRiskDebrisRow] = Field(default_factory=list)
    debris_altitudes_km: list[float] = Field(
        default_factory=list,
        description=(
            "Mean shell altitudes [km] of the §5 scored debris set, for the §5b "
            "고도별 잔해 밀도 chart only. Same selection as debris_risk_counts. "
            "Chart-only — deliberately NOT carried into the LLM facts (sanitize.py)."
        ),
    )


# --- §6 / §7 LLM prose contract -----------------------------------------------


class AnalysisItem(BaseModel):
    """One §6 일일 분석 내용 entry (LLM prose)."""

    detail: str = Field(description="상세 분석 내용.")
    cause_forecast: str = Field(description="원인 및 예상 분석.")


class ReportProse(BaseModel):
    """LLM output contract — narrative for §6 분석 and §7 대응 작전."""

    analysis_items: list[AnalysisItem] = Field(default_factory=list)
    response_ops: list[str] = Field(default_factory=list, description="대응 작전 추진 내용 항목.")


# --- Web-supplied images contract ---------------------------------------------


class ReportImages(BaseModel):
    """Web-supplied image bytes (rendered by the web layer, not the engine).

    All optional so the pipeline can run before images arrive.
    """

    country_globes: dict[str, bytes] = Field(
        default_factory=dict, description="3D globe snapshot per country code (NK/CN/RU/JP)."
    )
    debris_density: bytes | None = Field(default=None, description="§5b 고도별 잔해 밀도 chart.")
    debris_heatmap: bytes | None = Field(default=None, description="§5b 2D 잔해 밀도 히트맵.")
