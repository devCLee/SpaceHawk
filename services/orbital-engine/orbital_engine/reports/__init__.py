"""Daily space-operations report pipeline (HWPX).

The deterministic data layer only: ``assembler.assemble_daily`` gathers a
fully-typed :class:`~orbital_engine.reports.schemas.DailyReportPayload` (numbers
only) for a report date, reusing the pure pass geometry in
:mod:`~orbital_engine.reports.passes` (R2). Later tasks (R4-R7) layer on
:class:`ReportProse` (LLM), :class:`ReportImages` (web-supplied), HWPX fill, and
the task router; those modules are deliberately *not* imported here yet so the
package imports cleanly while they are still out of sync with the new schema.
No network, LLM, or randomness lives in the data layer.
"""

from orbital_engine.reports.assembler import assemble_daily
from orbital_engine.reports.charts import render_debris_density
from orbital_engine.reports.hwpx_filler import (
    FillError,
    fill_daily_report,
)
from orbital_engine.reports.narrative import (
    SectionError,
    write_report_prose,
)
from orbital_engine.reports.passes import (
    KARI,
    Observer,
    PassGeometry,
    predict_passes,
)
from orbital_engine.reports.sanitize import (
    LLMFacts,
    SanitizeResult,
    to_llm_facts,
)
from orbital_engine.reports.schemas import (
    AnalysisItem,
    ConjunctionRow,
    CountryActivity,
    DailyReportPayload,
    DebrisRiskCounts,
    HighRiskDebrisRow,
    ReportCountry,
    ReportImages,
    ReportProse,
    SatellitePass,
    WatchlistRow,
)

__all__ = [
    "KARI",
    "AnalysisItem",
    "ConjunctionRow",
    "CountryActivity",
    "DailyReportPayload",
    "DebrisRiskCounts",
    "FillError",
    "HighRiskDebrisRow",
    "LLMFacts",
    "Observer",
    "PassGeometry",
    "ReportCountry",
    "ReportImages",
    "ReportProse",
    "SanitizeResult",
    "SatellitePass",
    "SectionError",
    "WatchlistRow",
    "assemble_daily",
    "fill_daily_report",
    "predict_passes",
    "render_debris_density",
    "to_llm_facts",
    "write_report_prose",
]
