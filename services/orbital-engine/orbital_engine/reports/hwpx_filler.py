"""Fill the daily-report HWPX template with payload data and chart images (T5).

The LLM never touches XML. This module is the *only* place that knows how the
:class:`~orbital_engine.reports.schemas.DailyReportPayload` (plus LLM prose and
rendered chart PNGs) maps onto the OWPML template's table cells. Everything is
driven by a declarative :data:`SLOTMAP`, so callers hand us typed data and get
HWPX bytes back.

How the template is addressed
=============================
``python-hwpx`` exposes two label-based navigation primitives (verified against
2.11.1):

* ``fill_by_path({"<label> > <dir> > ...": value})`` — finds the *single* cell
  whose text equals ``<label>`` (across all tables, whitespace-collapsed,
  case-folded), walks the given directions (``up``/``down``/``left``/``right``),
  and sets the destination cell's text. It returns
  ``{"applied": [...], "failed": [...], "applied_count": int, "failed_count": int}``.
  A label that matches zero or *more than one* cell is reported in ``failed``
  with reason ``"label not found"`` / ``"ambiguous label"`` — it never guesses.

* ``find_cell_by_label(label, direction)`` — returns
  ``{"matches": [{"table_index", "label_cell", "target_cell"}, ...], "count": int}``
  so we can locate the target cell for a chart image.

Because both primitives key off *globally unique* label text, the template must
carry a distinct anchor label next to (above/left of) every fill target. The
shipped ``daily_report.hwpx`` does **not** yet (its tables use repeated column
headers like ``국가`` / ``통과 시점`` and blank data cells); the slotmap below names
the exact labels the user must add. See the T5 report / ``tests`` for the
synthetic template that exercises this logic end-to-end.

Images
======
A chart PNG is embedded in two steps (the paragraph-level ``add_picture`` takes a
binary-item id, not raw bytes): ``doc.add_image(png, "png") -> "BIN0001"`` then
``cell.paragraphs[0].add_picture(item_id, width=hwpunit, height=hwpunit)``. Sizes
are HWPUNIT (1/7200 inch); :data:`_HWPUNIT_PER_MM` converts from millimetres.

Failure policy (CRITICAL)
=========================
A half-filled report is worse than no report. Every targeted slot must apply:
:func:`fill_daily_report` raises :class:`FillError` listing the offenders if
``fill_by_path`` reports any failure, if any expected text slot was not applied,
or if any chart anchor does not resolve to exactly one cell / fails to embed.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib import resources

from hwpx import HwpxDocument
from hwpx.oxml import HwpxOxmlTable
from hwpx.tools.table_navigation import _collect_document_tables

from orbital_engine.reports.schemas import DailyReportPayload

# HWPUNIT is 1/7200 inch; convert millimetres for human-friendly chart sizing.
_HWPUNIT_PER_MM = 7200.0 / 25.4

# Default chart box inside a template cell (mm). Sized to the A4 content column.
_CHART_WIDTH_MM = 150.0
_CHART_HEIGHT_MM = 95.0

# The default template ships as a package asset so the Celery worker finds it
# regardless of CWD (loaded via importlib.resources, never a relative path).
_TEMPLATE_PACKAGE = "orbital_engine.reports.assets"
_TEMPLATE_RESOURCE = "daily_report.hwpx"


class FillError(Exception):
    """A report slot could not be filled; the report must not ship half-filled.

    Carries the list of offending slot/anchor descriptions so the caller can log
    exactly what went wrong (missing label, ambiguous label, failed embed, ...).
    """

    def __init__(self, message: str, *, slots: list[str] | None = None) -> None:
        self.slots = slots or []
        if self.slots:
            message = f"{message}: {', '.join(self.slots)}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ChartSlot:
    """Where a chart PNG goes: the unique anchor label and the step to its cell.

    ``label`` must match exactly one cell in the template; ``direction`` (one of
    ``up``/``down``/``left``/``right``) walks from that label cell to the image
    cell. ``chart_key`` selects the PNG from the ``charts`` mapping.
    """

    chart_key: str
    label: str
    direction: str = "down"
    width_mm: float = _CHART_WIDTH_MM
    height_mm: float = _CHART_HEIGHT_MM


@dataclass(frozen=True, slots=True)
class SlotMap:
    """The declarative template contract: text paths + chart anchors.

    ``text_paths`` maps a logical slot name to a ``fill_by_path`` path string
    (``"<label> > <dir> > ..."``). ``charts`` lists the image anchors. The two
    namespaces are independent; both must fully apply or :func:`fill_daily_report`
    raises.
    """

    text_paths: Mapping[str, str]
    charts: tuple[ChartSlot, ...]


# --------------------------------------------------------------------------- #
# The daily-report slotmap.
#
# These are the UNIQUE anchor labels the template must contain. The shipped
# daily_report.hwpx does not have them yet (its tables repeat column headers and
# leave data cells blank); add a distinct label cell next to each target before
# this default slotmap can fill the real template. Until then, callers pass their
# own SlotMap (the tests build a synthetic template that carries these labels).
# --------------------------------------------------------------------------- #
SLOTMAP = SlotMap(
    text_paths={
        # Cover / header.
        "report_date": "보고일자 > right",
        # §1 surveillance totals (single summary cell next to a unique label).
        "surveillance_total": "감시위성 합계 > right",
        # §2 top conjunction (most severe pair) — single-row summary.
        "top_conjunction_pair": "최우선 근접 위성 > right",
        "top_conjunction_miss_km": "최우선 근접 거리 > right",
        # §5 country breakdown leader.
        "top_country": "최다 보유국 > right",
        # Prose sections (LLM output).
        "prose_overview": "개요 본문 > down",
        "prose_analysis": "분석내용 본문 > down",
        "prose_outlook": "향후추진 본문 > down",
    },
    charts=(
        ChartSlot("altitude_decay", "고도 변화 도표", "down"),
        ChartSlot("longitude_date", "경도-일자 도표", "down"),
        ChartSlot("relative_position", "상대위치 도표", "down"),
        ChartSlot("orbit_3d", "3D 궤도 도표", "down"),
    ),
)


def _derive_text_values(payload: DailyReportPayload, prose: Mapping[str, str]) -> dict[str, str]:
    """Compute the string value for every text slot in :data:`SLOTMAP`.

    Pure and deterministic. Summaries pick the single most relevant record (most
    severe conjunction, largest country bucket) so each maps to one template cell.
    Empty sections still yield a value ("정보 없음"), never a missing slot.
    """
    values: dict[str, str] = {}

    values["report_date"] = _format_date(payload.report_date)

    surveillance_total = sum(row.count for row in payload.surveillance_categories)
    values["surveillance_total"] = str(surveillance_total)

    if payload.conjunctions:
        top = min(payload.conjunctions, key=lambda c: c.miss_distance_km)
        values["top_conjunction_pair"] = f"{top.primary_name} / {top.secondary_name}"
        values["top_conjunction_miss_km"] = f"{top.miss_distance_km:.3f}"
    else:
        values["top_conjunction_pair"] = "정보 없음"
        values["top_conjunction_miss_km"] = "정보 없음"

    if payload.country_breakdown:
        leader = max(payload.country_breakdown, key=lambda c: c.count)
        values["top_country"] = leader.owner_name or leader.owner_code
    else:
        values["top_country"] = "정보 없음"

    values["prose_overview"] = prose.get("개요", "").strip() or "정보 없음"
    values["prose_analysis"] = prose.get("분석내용", "").strip() or "정보 없음"
    values["prose_outlook"] = prose.get("향후추진", "").strip() or "정보 없음"

    return values


def _format_date(value: date) -> str:
    """Render the report date as ``YYYY. MM. DD.`` (the template's date style)."""
    return f"{value.year}. {value.month:02d}. {value.day:02d}."


def _load_default_template() -> bytes:
    """Read the bundled template as bytes via importlib.resources (CWD-safe)."""
    return resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_RESOURCE).read_bytes()


def _fill_text_slots(
    doc: HwpxDocument,
    slotmap: SlotMap,
    values: Mapping[str, str],
) -> None:
    """Apply every text slot in one batch; raise FillError on any miss.

    Builds the ``{path: value}`` mapping from the slotmap, runs ``fill_by_path``,
    then verifies the library reported zero failures AND that every requested path
    actually landed in ``applied`` (defence in depth against a future library that
    silently drops a path).
    """
    if not slotmap.text_paths:
        return

    mappings: dict[str, str] = {}
    path_to_slot: dict[str, str] = {}
    for slot_name, path in slotmap.text_paths.items():
        if slot_name not in values:
            raise FillError("no value derived for text slot", slots=[slot_name])
        mappings[path] = values[slot_name]
        path_to_slot[path] = slot_name

    result = doc.fill_by_path(mappings)

    failures: list[str] = []
    for failure in result["failed"]:
        path = failure["path"]
        slot_name = path_to_slot.get(path, path)
        failures.append(f"{slot_name} [{path!r}: {failure['reason']}]")

    applied_paths = {entry["path"] for entry in result["applied"]}
    for path, slot_name in path_to_slot.items():
        if path not in applied_paths and path not in {f["path"] for f in result["failed"]}:
            failures.append(f"{slot_name} [{path!r}: not applied]")

    if failures:
        raise FillError("text slot(s) failed to fill", slots=failures)


def _embed_charts(
    doc: HwpxDocument,
    slotmap: SlotMap,
    charts: Mapping[str, bytes],
) -> None:
    """Embed each chart PNG into its anchor cell; raise FillError on any miss.

    For every :class:`ChartSlot` the anchor label must resolve to exactly one
    cell (``find_cell_by_label`` ``count == 1``); the PNG is added to the document
    and inserted into that cell's first paragraph as an inline picture. A missing
    chart key, an absent/ambiguous anchor, or an embed exception all raise.
    """
    if not slotmap.charts:
        return

    failures: list[str] = []

    for slot in slotmap.charts:
        if slot.chart_key not in charts:
            failures.append(f"{slot.chart_key} [no PNG supplied]")
            continue

        search = doc.find_cell_by_label(slot.label, slot.direction)
        if search["count"] != 1:
            failures.append(
                f"{slot.chart_key} [anchor {slot.label!r}: {search['count']} matches, want 1]"
            )
            continue

        match = search["matches"][0]
        target = match["target_cell"]
        try:
            _insert_picture(doc, match["table_index"], target["row"], target["col"], slot, charts)
        except FillError:
            raise
        except Exception as exc:  # noqa: BLE001 - any embed failure must surface as FillError
            failures.append(f"{slot.chart_key} [embed failed: {exc}]")

    if failures:
        raise FillError("chart(s) failed to embed", slots=failures)


def _insert_picture(
    doc: HwpxDocument,
    table_index: int,
    row: int,
    col: int,
    slot: ChartSlot,
    charts: Mapping[str, bytes],
) -> None:
    """Add the PNG to the package and anchor it in the (table, row, col) cell."""
    table = _table_at(doc, table_index)
    cell = table.cell(row, col)
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        raise FillError("chart anchor cell has no paragraph", slots=[slot.chart_key])

    item_id = doc.add_image(charts[slot.chart_key], "png")
    paragraphs[0].add_picture(
        item_id,
        width=int(slot.width_mm * _HWPUNIT_PER_MM),
        height=int(slot.height_mm * _HWPUNIT_PER_MM),
    )


def _table_at(doc: HwpxDocument, table_index: int) -> HwpxOxmlTable:
    """Return the live OXML table at ``table_index`` (document order).

    Reuses the library's own collector so the index matches ``get_table_map`` /
    ``find_cell_by_label`` exactly (it recurses into nested tables in the same
    order the search primitives do).
    """
    indexed = _collect_document_tables(doc)
    if table_index >= len(indexed):
        raise FillError("chart anchor table out of range", slots=[str(table_index)])
    return indexed[table_index].table


def fill_daily_report(
    payload: DailyReportPayload,
    prose: Mapping[str, str],
    charts: Mapping[str, bytes],
    *,
    template_path: str | None = None,
    slotmap: SlotMap = SLOTMAP,
) -> bytes:
    """Fill the template with ``payload`` + ``prose`` + ``charts`` → HWPX bytes.

    ``prose`` maps section names (개요 / 분석내용 / 향후추진) to LLM-written text;
    ``charts`` maps chart keys (see :data:`SLOTMAP`) to PNG bytes. ``template_path``
    overrides the bundled asset (the default is loaded CWD-independently). Raises
    :class:`FillError` if any text slot or chart anchor cannot be filled — never
    returns a partially filled report.
    """
    template_bytes = (
        _load_default_template() if template_path is None else _read_template(template_path)
    )
    doc = HwpxDocument.open(io.BytesIO(template_bytes))

    values = _derive_text_values(payload, prose)
    _fill_text_slots(doc, slotmap, values)
    _embed_charts(doc, slotmap, charts)

    return doc.to_bytes()


def _read_template(template_path: str) -> bytes:
    """Read an explicit template path as bytes (test / override hook)."""
    with open(template_path, "rb") as handle:
        return handle.read()
