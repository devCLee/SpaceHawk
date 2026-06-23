"""Fill the daily-report HWPX template with payload data, prose, and web images (R6).

The LLM and the web never touch XML. This module is the *only* place that knows
how the :class:`~orbital_engine.reports.schemas.DailyReportPayload` (plus
:class:`ReportProse` and :class:`ReportImages`) maps onto the real OWPML template
``assets/daily_report.hwpx``. Callers hand us typed data and get HWPX bytes back.

How the template is addressed (verified against python-hwpx 2.11.1)
==================================================================
The shipped template's tables use *repeated* column headers (``국가`` / ``통과 시점`` /
``심각`` …), so label-addressing (``fill_by_path`` / ``find_cell_by_label``) is
ambiguous and unusable here. Instead we address tables by **document-order index**
— the order :func:`hwpx.tools.table_navigation._collect_document_tables` yields —
and cells by ``(row, col)`` via ``HwpxOxmlTable.set_cell_text(r, c, text,
logical=True)``.

The real template (10 tables) maps to report sections as :data:`_TABLES` records.
Every multi-row table ships with a header block + a *single* blank data row; the
library exposes no row-append API, so :func:`_ensure_rows` clones that blank
``<hp:tr>`` (rewriting each cell's ``rowAddr`` and clearing its text) and bumps the
table element's ``rowCnt`` — that is the supported way to grow a table here. There
is therefore **no fixed capacity cap**: N data items render N rows.

Images
======
Globe snapshots (one per country activity section) and the two debris charts are
supplied by the web as PNG bytes. Each is embedded in two steps: ``doc.add_image(
png, "png") -> item_id`` then ``cell.paragraphs[0].add_picture(item_id,
width=hwpunit, height=hwpunit)`` (HWPUNIT = 1/7200 inch). Images are *optional*:
a missing globe / density / heatmap leaves its anchor blank and is logged, never
fatal.

Prose
=====
§6 일일 분석 내용 and §7 대응 작전 추진 내용 are not tables — they are top-level
section paragraphs. We append fresh paragraphs after each heading via
``doc.add_paragraph`` so the narrative renders inline under the right heading.

Failure policy (CRITICAL)
=========================
A half-filled report is worse than no report. :func:`fill_daily_report` is
fail-closed on **data** structure: if the template does not expose the tables /
cells the data needs (wrong table count, an out-of-range cell), it raises
:class:`FillError` listing exactly what failed. Missing *images* never fail.
"""

from __future__ import annotations

import copy
import io
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources

from hwpx import HwpxDocument
from hwpx.oxml import HwpxOxmlTable
from hwpx.tools.table_navigation import _collect_document_tables

from orbital_engine.reports.schemas import (
    DailyReportPayload,
    ReportCountry,
    ReportImages,
    ReportProse,
)

logger = logging.getLogger(__name__)

# lxml namespace for the OWPML paragraph schema (table/row/cell elements).
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# HWPUNIT is 1/7200 inch; convert millimetres for human-friendly image sizing.
_HWPUNIT_PER_MM = 7200.0 / 25.4

# Default globe / debris image box inside a template cell (mm).
_GLOBE_WIDTH_MM = 150.0
_GLOBE_HEIGHT_MM = 90.0
_DEBRIS_WIDTH_MM = 78.0
_DEBRIS_HEIGHT_MM = 70.0

# The default template ships as a package asset so the Celery worker finds it
# regardless of CWD (loaded via importlib.resources, never a relative path).
_TEMPLATE_PACKAGE = "orbital_engine.reports.assets"
_TEMPLATE_RESOURCE = "daily_report.hwpx"

# --------------------------------------------------------------------------- #
# Template layout (document-order table index -> section), confirmed by STEP-1
# introspection of the real assets/daily_report.hwpx (10 tables):
#
#   [0] 1x1  cover (title + date)            -> not filled here (static cover)
#   [1] 2x6  §1 관심목록 등록 위성 현황         국가|LEO|MEO|GEO|HEO|합계   (hdr row 0)
#   [2] 4x5  §2 북한 위성 활동                  pass tbl; globe img r1; data r3
#                                            위성명|통과시점|최근접|방위고도|비고
#   [3] 4x5  §3 중국 위성 활동                  (same shape)
#   [4] 4x5  §3 러시아 위성 활동                (same shape)
#   [5] 4x5  §3 일본 위성 활동                  (same shape)
#   [6] 2x6  §4 근접 및 충돌 현황              위성명|객체명|시각|거리|확률|구분 (hdr row 0)
#   [7] 2x4  §5a 충돌 위험도                   심각|높음|보통|낮음           (hdr row 0)
#   [8] 2x2  §5b 잔해 밀도 + 히트맵           density img r1c0 / heatmap r1c1
#   [9] 2x7  §5c 고위험 잔해 현황              국가|잔해명|위험등급|RCS|고도|주기|근/원 (hdr 0)
# --------------------------------------------------------------------------- #
_COVER_TABLE = 0
_WATCHLIST_TABLE = 1
_CONJUNCTION_TABLE = 6
_RISK_COUNT_TABLE = 7
_DEBRIS_IMAGE_TABLE = 8
_HIGH_RISK_TABLE = 9

# Cover (table[0], cell 0,0) holds the title on paragraph 0 and a bracketed date
# string on paragraph 1, e.g. "[ 2026. 06. 22. (화) ]". We rewrite that one
# paragraph; the title paragraph is preserved untouched. Korean weekday is indexed
# by date.weekday() (Mon=0 .. Sun=6).
_COVER_DATE_RE = re.compile(r"\[\s*\d{4}\.\s*\d{2}\.\s*\d{2}\.\s*\([월화수목금토일]\)\s*\]")
_WEEKDAYS_KR = ("월", "화", "수", "목", "금", "토", "일")

# Country activity tables in NK/CN/RU/JP order; image cell at (row 1, col 0),
# first data row at index 3.
_COUNTRY_TABLES: dict[ReportCountry, int] = {
    ReportCountry.NORTH_KOREA: 2,
    ReportCountry.CHINA: 3,
    ReportCountry.RUSSIA: 4,
    ReportCountry.JAPAN: 5,
}
_COUNTRY_IMAGE_CELL = (1, 0)
_COUNTRY_DATA_ROW = 3

# Heading text of the two prose sections (top-level section paragraphs). The
# leading char is a Hancom dingbat bullet ( / ); we match on the
# trailing Korean phrase so the bullet variant does not matter.
_ANALYSIS_HEADING = "일일 분석 내용"
_RESPONSE_HEADING = "대응 작전 추진 내용"

# The smallest table count a real daily-report template must have.
_MIN_TABLES = 10


class FillError(Exception):
    """A report data slot could not be filled; the report must not ship half-filled.

    Carries the list of offending slot/anchor descriptions so the caller can log
    exactly what went wrong (template too small, cell out of range, ...). Missing
    *images* never raise — they are best-effort and web-supplied.
    """

    def __init__(self, message: str, *, slots: list[str] | None = None) -> None:
        self.slots = slots or []
        if self.slots:
            message = f"{message}: {', '.join(self.slots)}"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _ImageBox:
    """Target cell + render size (mm) for one embedded picture."""

    table_index: int
    row: int
    col: int
    width_mm: float
    height_mm: float


# --------------------------------------------------------------------------- #
# value formatting (pure, deterministic)
# --------------------------------------------------------------------------- #


def _fmt_dt(value: datetime | None) -> str:
    """Render a UTC datetime as ``YYYY-MM-DD HH:MMZ`` (empty for None)."""
    if value is None:
        return ""
    return f"{value:%Y-%m-%d %H:%M}Z"


def _fmt_num(value: float | None, digits: int = 2) -> str:
    """Render a float with ``digits`` decimals (empty for None)."""
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _fmt_prob(value: float | None) -> str:
    """Render a collision probability in scientific notation (empty for None)."""
    if value is None:
        return ""
    return f"{value:.2e}"


def _fmt_rcs(value: str | float | None) -> str:
    """Render an RCS size (class string or numeric area) (empty for None)."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)


def _fmt_apsides(perigee: float | None, apogee: float | None) -> str:
    """Render ``perigee/apogee`` km, omitting absent sides (empty if both None)."""
    if perigee is None and apogee is None:
        return ""
    return f"{_fmt_num(perigee)}/{_fmt_num(apogee)}"


def _country_label(code: str, name: str | None) -> str:
    """Render a country cell as the resolved name, falling back to the code."""
    return name or code


def _fmt_cover_date(value: date) -> str:
    """Render a date Korean-style as ``YYYY. MM. DD. (요일)`` (no brackets)."""
    return f"{value.year:04d}. {value.month:02d}. {value.day:02d}. ({_WEEKDAYS_KR[value.weekday()]})"


# --------------------------------------------------------------------------- #
# table / row primitives
# --------------------------------------------------------------------------- #


def _load_default_template() -> bytes:
    """Read the bundled template as bytes via importlib.resources (CWD-safe)."""
    return resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_RESOURCE).read_bytes()


def _read_template(template_path: str) -> bytes:
    """Read an explicit template path as bytes (test / override hook)."""
    with open(template_path, "rb") as handle:
        return handle.read()


def _table_at(doc: HwpxDocument, table_index: int) -> HwpxOxmlTable:
    """Return the live OXML table at ``table_index`` (document order).

    Raises :class:`FillError` if the template has fewer tables than expected, so
    a structurally wrong template fails closed rather than mis-filling.
    """
    indexed = _collect_document_tables(doc)
    if table_index >= len(indexed):
        raise FillError(
            "template table missing (structure mismatch)",
            slots=[f"table[{table_index}] of {len(indexed)}"],
        )
    return indexed[table_index].table


def _ensure_rows(doc: HwpxDocument, table_index: int, data_row: int, n_rows: int) -> HwpxOxmlTable:
    """Grow the table so it has exactly ``n_rows`` data rows below ``data_row``.

    The template ships one blank data row at index ``data_row``; the library has
    no row-append API, so we deep-copy that ``<hp:tr>`` (rewriting each cell's
    ``rowAddr`` and clearing its text), insert it after the last row, and bump the
    table element's ``rowCnt``. No capacity cap: N items -> N rows. Returns the
    table re-resolved against the grown element.
    """
    table = _table_at(doc, table_index)
    existing_rows = table.element.findall(f"{_HP}tr")
    if data_row >= len(existing_rows):
        raise FillError(
            "template data row missing (structure mismatch)",
            slots=[f"table[{table_index}] data row {data_row}"],
        )

    target_total = data_row + max(n_rows, 1)
    src_tr = existing_rows[data_row]
    last_tr = existing_rows[-1]
    current_index = len(existing_rows)
    while current_index < target_total:
        new_tr = copy.deepcopy(src_tr)
        for cell in new_tr.findall(f"{_HP}tc"):
            addr = cell.find(f"{_HP}cellAddr")
            if addr is not None:
                addr.set("rowAddr", str(current_index))
            for text_node in cell.findall(f".//{_HP}t"):
                text_node.text = ""
        last_tr.addnext(new_tr)
        last_tr = new_tr
        current_index += 1

    table.element.set("rowCnt", str(max(target_total, len(existing_rows))))
    # Re-resolve so the cell grid reflects the appended rows.
    return _table_at(doc, table_index)


def _set_cell(table: HwpxOxmlTable, row: int, col: int, value: str, *, where: str) -> None:
    """Set one cell's text, raising FillError (with ``where``) if unaddressable."""
    try:
        table.set_cell_text(row, col, value, logical=True)
    except (IndexError, ValueError, KeyError) as exc:
        raise FillError("cell not addressable (structure mismatch)", slots=[f"{where}: {exc}"]) from exc


def _fill_rows(
    doc: HwpxDocument,
    table_index: int,
    data_row: int,
    rows: Sequence[Sequence[str]],
    *,
    section: str,
) -> None:
    """Clone/grow the table to hold ``rows`` and write each row's cells.

    Empty ``rows`` leaves the single blank template row untouched. Every cell
    write is fail-closed (out-of-range -> FillError tagged with ``section``).
    """
    if not rows:
        return
    table = _ensure_rows(doc, table_index, data_row, len(rows))
    for offset, values in enumerate(rows):
        r = data_row + offset
        for c, value in enumerate(values):
            _set_cell(table, r, c, value, where=f"{section} r{r}c{c}")


# --------------------------------------------------------------------------- #
# section builders (payload -> list[list[str]])
# --------------------------------------------------------------------------- #


def _watchlist_rows(payload: DailyReportPayload) -> list[list[str]]:
    """§1 rows: one per country plus the grand-total row (if present)."""
    rows: list[list[str]] = []
    for entry in payload.watchlist_matrix:
        rows.append(
            [
                _country_label(entry.country_code, entry.country_name),
                str(entry.leo),
                str(entry.meo),
                str(entry.geo),
                str(entry.heo),
                str(entry.total),
            ]
        )
    if payload.watchlist_total is not None:
        total = payload.watchlist_total
        rows.append(
            [
                _country_label(total.country_code, total.country_name),
                str(total.leo),
                str(total.meo),
                str(total.geo),
                str(total.heo),
                str(total.total),
            ]
        )
    return rows


def _pass_rows(activity_passes: Sequence) -> list[list[str]]:
    """§2/§3 rows for one country: 위성명 | 통과 시점 | 최근접 시각/거리 | 방위/고도 | 비고."""
    rows: list[list[str]] = []
    for p in activity_passes:
        closest = _fmt_dt(p.closest_time)
        distance = _fmt_num(p.closest_distance_km)
        closest_cell = f"{closest} / {distance} km" if (closest or distance) else ""
        az = _fmt_num(p.azimuth_deg, 1)
        el = _fmt_num(p.elevation_deg, 1)
        az_el = f"{az} / {el}" if (az or el) else ""
        rows.append([p.satellite_name, _fmt_dt(p.pass_time), closest_cell, az_el, p.remarks or ""])
    return rows


def _conjunction_rows(payload: DailyReportPayload) -> list[list[str]]:
    """§4 rows: 위성명 | 객체명 | 최근접 시각 | 거리 | 충돌 확률 | 위험 구분."""
    return [
        [
            row.satellite_name,
            row.object_name,
            _fmt_dt(row.tca),
            _fmt_num(row.distance_km, 3),
            _fmt_prob(row.probability),
            row.risk_category,
        ]
        for row in payload.conjunctions
    ]


def _high_risk_rows(payload: DailyReportPayload) -> list[list[str]]:
    """§5c rows: 국가 | 잔해명 | 위험등급 | RCS | 평균 고도 | 주기 | 근/원지점."""
    return [
        [
            _country_label(row.country_code, row.country_name),
            row.debris_name,
            row.risk_grade,
            _fmt_rcs(row.rcs_size),
            _fmt_num(row.mean_altitude_km),
            _fmt_num(row.period_min),
            _fmt_apsides(row.perigee_km, row.apogee_km),
        ]
        for row in payload.high_risk_debris
    ]


# --------------------------------------------------------------------------- #
# fillers
# --------------------------------------------------------------------------- #


def _fill_cover(doc: HwpxDocument, report_date: date) -> None:
    """Replace the cover's bracketed date with ``report_date`` (Korean-formatted).

    The cover (table[0], cell 0,0) carries the title on one paragraph and a
    ``[ YYYY. MM. DD. (요일) ]`` date on another. We rewrite only the paragraph
    matching :data:`_COVER_DATE_RE`, preserving the title paragraph verbatim.

    The cover is cosmetic: if the table / cell / date paragraph is absent, we log
    a warning and continue (data tables remain fail-closed elsewhere).
    """
    replacement = f"[ {_fmt_cover_date(report_date)} ]"
    try:
        cover = _table_at(doc, _COVER_TABLE)
        cell = cover.cell(0, 0)
        for para in cell.paragraphs:
            if _COVER_DATE_RE.search(para.text or ""):
                para.text = replacement
                return
    except (FillError, IndexError, ValueError, KeyError) as exc:
        logger.warning("cover date not filled (cover cell unreachable): %s", exc)
        return
    logger.warning("cover date pattern not found; cover date left unchanged")


def _fill_tables(doc: HwpxDocument, payload: DailyReportPayload) -> None:
    """Fill every data table (fail-closed on structure)."""
    _fill_rows(
        doc, _WATCHLIST_TABLE, 1, _watchlist_rows(payload), section="watchlist"
    )

    activity_by_country = {a.country_code: a for a in payload.country_activity}
    for country, table_index in _COUNTRY_TABLES.items():
        activity = activity_by_country.get(country.value)
        passes = activity.passes if activity is not None else []
        _fill_rows(
            doc,
            table_index,
            _COUNTRY_DATA_ROW,
            _pass_rows(passes),
            section=f"passes[{country.value}]",
        )

    _fill_rows(
        doc, _CONJUNCTION_TABLE, 1, _conjunction_rows(payload), section="conjunctions"
    )

    counts = payload.debris_risk_counts
    risk_table = _table_at(doc, _RISK_COUNT_TABLE)
    for col, value in enumerate(
        (counts.critical, counts.high, counts.moderate, counts.low)
    ):
        _set_cell(risk_table, 1, col, str(value), where=f"risk_counts c{col}")

    _fill_rows(
        doc, _HIGH_RISK_TABLE, 1, _high_risk_rows(payload), section="high_risk_debris"
    )


def _embed_image(doc: HwpxDocument, png: bytes, box: _ImageBox, *, what: str) -> None:
    """Embed one PNG into ``box``'s cell. Logs and skips on any embed problem."""
    try:
        table = _table_at(doc, box.table_index)
        cell = table.cell(box.row, box.col)
        paragraphs = list(cell.paragraphs)
        if not paragraphs:
            logger.warning("image anchor %s has no paragraph; skipping", what)
            return
        item_id = doc.add_image(png, "png")
        paragraphs[0].add_picture(
            item_id,
            width=int(box.width_mm * _HWPUNIT_PER_MM),
            height=int(box.height_mm * _HWPUNIT_PER_MM),
        )
    except Exception:  # noqa: BLE001 - images are best-effort; never fail the report
        logger.warning("failed to embed image %s; leaving anchor blank", what, exc_info=True)


def _embed_images(doc: HwpxDocument, images: ReportImages) -> None:
    """Embed the web-supplied globe / debris images; log (never raise) on misses."""
    for country, table_index in _COUNTRY_TABLES.items():
        png = images.country_globes.get(country.value)
        if png is None:
            logger.info("no globe snapshot supplied for %s; anchor left blank", country.value)
            continue
        row, col = _COUNTRY_IMAGE_CELL
        _embed_image(
            doc,
            png,
            _ImageBox(table_index, row, col, _GLOBE_WIDTH_MM, _GLOBE_HEIGHT_MM),
            what=f"globe[{country.value}]",
        )

    if images.debris_density is None:
        logger.info("no debris-density image supplied; anchor left blank")
    else:
        _embed_image(
            doc,
            images.debris_density,
            _ImageBox(_DEBRIS_IMAGE_TABLE, 1, 0, _DEBRIS_WIDTH_MM, _DEBRIS_HEIGHT_MM),
            what="debris_density",
        )

    if images.debris_heatmap is None:
        logger.info("no debris-heatmap image supplied; anchor left blank")
    else:
        _embed_image(
            doc,
            images.debris_heatmap,
            _ImageBox(_DEBRIS_IMAGE_TABLE, 1, 1, _DEBRIS_WIDTH_MM, _DEBRIS_HEIGHT_MM),
            what="debris_heatmap",
        )


def _insert_after_heading(doc: HwpxDocument, heading: str, lines: Sequence[str]) -> None:
    """Append ``lines`` as new paragraphs directly after the section ``heading``.

    Locates the top-level paragraph whose text ends with ``heading`` (the bullet
    glyph prefix is ignored) and inserts a fresh paragraph per line right after it
    so the prose renders under the correct section. Raises FillError if the
    heading paragraph is absent (the template is structurally wrong).
    """
    paragraphs = list(doc.paragraphs)
    anchor_el = None
    for para in paragraphs:
        text = (para.text or "").strip()
        if text.endswith(heading):
            anchor_el = para.element
            break
    if anchor_el is None:
        raise FillError("prose heading missing (structure mismatch)", slots=[heading])

    # Insert in order: each new paragraph goes right after the previous one.
    cursor = anchor_el
    for line in lines:
        new_para = doc.add_paragraph(line)
        cursor.addnext(new_para.element)
        cursor = new_para.element


def _fill_prose(doc: HwpxDocument, prose: ReportProse) -> None:
    """Insert §6 분석 내용 (detail + cause/forecast) and §7 대응 작전 항목."""
    analysis_lines: list[str] = []
    for index, item in enumerate(prose.analysis_items, start=1):
        analysis_lines.append(f"{index}. 상세 분석 내용: {item.detail}")
        analysis_lines.append(f"   원인 및 예상 분석: {item.cause_forecast}")
    _insert_after_heading(doc, _ANALYSIS_HEADING, analysis_lines)

    response_lines = [f"{index}. {op}" for index, op in enumerate(prose.response_ops, start=1)]
    _insert_after_heading(doc, _RESPONSE_HEADING, response_lines)


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #


def fill_daily_report(
    payload: DailyReportPayload,
    prose: ReportProse,
    images: ReportImages,
    *,
    template_path: str | None = None,
) -> bytes:
    """Fill the daily-report template with ``payload`` + ``prose`` + ``images``.

    Returns the filled HWPX as bytes. Data tables and prose headings are
    fail-closed: if the template cannot expose a required table / cell / heading,
    :class:`FillError` is raised listing exactly what was missing — never a
    partially filled report. Web-supplied ``images`` are best-effort: a missing
    globe / density / heatmap leaves its anchor blank and is logged, not raised.

    ``template_path`` overrides the bundled asset (loaded CWD-independently for
    Celery-worker safety).
    """
    template_bytes = (
        _load_default_template() if template_path is None else _read_template(template_path)
    )
    doc = HwpxDocument.open(io.BytesIO(template_bytes))

    # Fail closed early if the template is structurally too small.
    indexed = _collect_document_tables(doc)
    if len(indexed) < _MIN_TABLES:
        raise FillError(
            "template has too few tables (structure mismatch)",
            slots=[f"{len(indexed)} tables, need >= {_MIN_TABLES}"],
        )

    _fill_cover(doc, payload.report_date)
    _fill_tables(doc, payload)
    _fill_prose(doc, prose)
    _embed_images(doc, images)

    return doc.to_bytes()
