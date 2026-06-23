"""Daily space-situation report pipeline (HWPX).

T1 — the deterministic data layer only. ``assembler.assemble_daily`` gathers a
fully-typed :class:`~orbital_engine.reports.schemas.DailyReportPayload` from the
canonical catalog for a given report date; later tasks turn that payload into
LLM prose, charts, and a filled HWPX template. No network, LLM, or randomness
lives here.
"""

from orbital_engine.reports.assembler import assemble_daily
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

__all__ = [
    "ConjunctionRow",
    "CountryBreakdownEntry",
    "DailyReportPayload",
    "ManeuverDataStatus",
    "ManeuverEntry",
    "ReentryEntry",
    "SurveillanceCategoryCount",
    "SurveillanceObjectRow",
    "TimeSeriesPoint",
    "TimeSeriesSeries",
    "assemble_daily",
]
