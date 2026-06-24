"""Render the daily-report payload + prose + images into a PDF (replaces the HWPX
filler). The LLM and the web never touch layout: this module is the only place
that maps the typed :class:`~orbital_engine.reports.schemas.DailyReportPayload`
(plus :class:`ReportProse` and :class:`ReportImages`) onto the report's visual
format. Callers hand us typed data and get PDF bytes back.

Why PDF (and why HTML→PDF)
==========================
The prior HWPX path embedded images via ``python-hwpx`` and they rendered as
broken-image icons in Hancom; the embedded-image binding in OWPML is
underspecified by the alpha library and not verifiable without Hancom itself.
PDF image embedding is a solved problem and the output is verifiable in CI, so
the pipeline switched to PDF while keeping the exact same report sections.

We build an HTML/CSS document (Korean-aware font stack) and convert it with
WeasyPrint. HTML/CSS expresses the multi-table + embedded-image + prose layout
with far less code than a programmatic PDF canvas, and images embed trivially as
base64 ``data:`` URIs.

Two-function split
==================
:func:`build_report_html` is PURE (no native deps) and holds ALL layout logic,
so it is fully unit-testable on any host. :func:`render_daily_report_pdf` is the
thin HTML→PDF step; it imports WeasyPrint LAZILY (WeasyPrint needs Pango/cairo
native libs, present in the engine container but not necessarily on a dev box),
so importing this module — and therefore ``tasks`` — never requires those libs.

Images are best-effort: a missing globe / density / heatmap simply omits that
picture (a short placeholder note renders in its place), never fails the render —
mirroring the HWPX pipeline's image policy.
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Sequence

from jinja2 import Environment, select_autoescape
from PIL import Image

from orbital_engine.reports.formatting import (
    country_label,
    fmt_apsides,
    fmt_cover_date,
    fmt_dt,
    fmt_num,
    fmt_prob,
    fmt_rcs,
)
from orbital_engine.reports.schemas import (
    DailyReportPayload,
    ReportCountry,
    ReportImages,
    ReportProse,
    SatellitePass,
)

logger = logging.getLogger(__name__)

# Report cover title (matches the HWPX template cover).
_REPORT_TITLE = "일일 우주작전현황 보고"

# Country render order + headings. §2 is 북한; §3 groups the 주변국 (중/러/일).
_COUNTRY_ORDER: tuple[tuple[ReportCountry, str, str], ...] = (
    (ReportCountry.NORTH_KOREA, "2", "북한 위성 활동 현황"),
    (ReportCountry.CHINA, "3", "중국 위성 활동 현황"),
    (ReportCountry.RUSSIA, "3", "러시아 위성 활동 현황"),
    (ReportCountry.JAPAN, "3", "일본 위성 활동 현황"),
)

# §1 grid columns + the empty-state message (mirrors the HWPX filler).
_WATCHLIST_HEADERS = ("국가", "LEO", "MEO", "GEO", "HEO", "합계")
_WATCHLIST_EMPTY_MSG = "등록된 관심 목록 위성 데이터가 없습니다."
_PASS_HEADERS = ("위성명", "통과 시점", "최근접 시각 / 거리", "방위 / 고도", "비고")
_CONJUNCTION_HEADERS = ("위성명", "객체명", "최근접 시각", "거리(km)", "충돌 확률", "위험 구분")
_HIGH_RISK_HEADERS = ("국가", "잔해명", "위험등급", "RCS", "평균 고도(km)", "주기(min)", "근/원지점(km)")
_RISK_COUNT_HEADERS = ("심각", "높음", "보통", "낮음")
_NO_DATA_MSG = "해당 사항 없음"

# Korean-aware font stack. fonts-nanum is installed in the engine image; the
# generic fallbacks keep ASCII legible if no CJK face is present.
_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<style>
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: "NanumGothic", "Noto Sans CJK KR", "Malgun Gothic", sans-serif;
         font-size: 10pt; color: #111; }
  h1 { text-align: center; font-size: 18pt; margin: 0 0 6pt; }
  .cover-date { text-align: center; font-size: 12pt; margin: 0 0 18pt; }
  h2 { font-size: 12pt; margin: 14pt 0 6pt; border-bottom: 1.5pt solid #333; padding-bottom: 2pt; }
  section { page-break-inside: avoid; }
  table { width: 100%; border-collapse: collapse; margin: 4pt 0 8pt; }
  th, td { border: 0.5pt solid #888; padding: 3pt 4pt; text-align: center; vertical-align: middle; }
  th { background: #e8eef5; font-weight: bold; }
  td.left { text-align: left; }
  tr.total td { background: #f3f3f3; font-weight: bold; }
  .no-data { color: #666; font-style: italic; }
  .globe { text-align: center; margin: 4pt 0; }
  .globe img { max-width: 150mm; max-height: 90mm; }
  .debris { display: flex; gap: 8mm; justify-content: center; align-items: flex-start; }
  .debris figure { margin: 0; text-align: center; }
  .debris img { max-width: 80mm; max-height: 72mm; }
  .img-missing { color: #999; font-style: italic; padding: 6pt; }
  .prose-item { margin: 0 0 6pt; }
  .prose-item .label { font-weight: bold; }
  ol.ops { margin: 4pt 0 8pt 18pt; }
  ol.ops li { margin: 0 0 3pt; }
</style>
</head>
<body>
  <h1>{{ title }}</h1>
  <div class="cover-date">{{ cover_date }}</div>

  <section>
    <h2>1. 관심목록 등록 위성 현황</h2>
    <table>
      <thead><tr>{% for h in watchlist_headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody>
      {% if watchlist_rows %}
        {% for row in watchlist_rows %}
        <tr{% if row.total %} class="total"{% endif %}>{% for c in row.cells %}<td>{{ c }}</td>{% endfor %}</tr>
        {% endfor %}
      {% else %}
        <tr><td class="no-data" colspan="{{ watchlist_headers|length }}">{{ watchlist_empty }}</td></tr>
      {% endif %}
      </tbody>
    </table>
  </section>

  {% for country in countries %}
  <section>
    <h2>{{ country.section }}. {{ country.heading }}</h2>
    <div class="globe">
      {% if country.globe %}<img src="{{ country.globe }}"/>{% else %}<span class="img-missing">위성 위치 스냅샷 없음</span>{% endif %}
    </div>
    <table>
      <thead><tr>{% for h in pass_headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody>
      {% if country.passes %}
        {% for row in country.passes %}
        <tr>{% for c in row %}<td{% if loop.index0 == 0 %} class="left"{% endif %}>{{ c }}</td>{% endfor %}</tr>
        {% endfor %}
      {% else %}
        <tr><td class="no-data" colspan="{{ pass_headers|length }}">{{ no_data }}</td></tr>
      {% endif %}
      </tbody>
    </table>
  </section>
  {% endfor %}

  <section>
    <h2>4. 근접 및 충돌 현황</h2>
    <table>
      <thead><tr>{% for h in conjunction_headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody>
      {% if conjunctions %}
        {% for row in conjunctions %}
        <tr>{% for c in row %}<td{% if loop.index0 < 2 %} class="left"{% endif %}>{{ c }}</td>{% endfor %}</tr>
        {% endfor %}
      {% else %}
        <tr><td class="no-data" colspan="{{ conjunction_headers|length }}">{{ no_data }}</td></tr>
      {% endif %}
      </tbody>
    </table>
  </section>

  <section>
    <h2>5. 한반도 근처 우주 잔해 현황</h2>
    <h3 style="font-size:11pt;margin:8pt 0 4pt;">5a. 충돌 위험도</h3>
    <table>
      <thead><tr>{% for h in risk_headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody><tr>{% for c in risk_counts %}<td>{{ c }}</td>{% endfor %}</tr></tbody>
    </table>
    <h3 style="font-size:11pt;margin:8pt 0 4pt;">5b. 고도별 잔해 밀도 / 2D 잔해 밀도 히트맵</h3>
    <div class="debris">
      <figure>{% if debris_density %}<img src="{{ debris_density }}"/>{% else %}<span class="img-missing">밀도 차트 없음</span>{% endif %}<figcaption>고도별 잔해 밀도</figcaption></figure>
      <figure>{% if debris_heatmap %}<img src="{{ debris_heatmap }}"/>{% else %}<span class="img-missing">히트맵 없음</span>{% endif %}<figcaption>2D 잔해 밀도 히트맵</figcaption></figure>
    </div>
    <h3 style="font-size:11pt;margin:8pt 0 4pt;">5c. 고위험 잔해 현황</h3>
    <table>
      <thead><tr>{% for h in high_risk_headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
      <tbody>
      {% if high_risk %}
        {% for row in high_risk %}
        <tr>{% for c in row %}<td{% if loop.index0 < 2 %} class="left"{% endif %}>{{ c }}</td>{% endfor %}</tr>
        {% endfor %}
      {% else %}
        <tr><td class="no-data" colspan="{{ high_risk_headers|length }}">{{ no_data }}</td></tr>
      {% endif %}
      </tbody>
    </table>
  </section>

  <section>
    <h2>6. 일일 분석 내용</h2>
    {% if analysis %}
      {% for item in analysis %}
      <div class="prose-item">
        <div><span class="label">{{ item.idx }}. 상세 분석 내용:</span> {{ item.detail }}</div>
        <div><span class="label">원인 및 예상 분석:</span> {{ item.cause_forecast }}</div>
      </div>
      {% endfor %}
    {% else %}<div class="no-data">{{ no_data }}</div>{% endif %}
  </section>

  <section>
    <h2>7. 대응 작전 추진 내용</h2>
    {% if response_ops %}
      <ol class="ops">{% for op in response_ops %}<li>{{ op }}</li>{% endfor %}</ol>
    {% else %}<div class="no-data">{{ no_data }}</div>{% endif %}
  </section>
</body>
</html>
"""


def _img_data_uri(data: bytes | None) -> str | None:
    """Encode image bytes as a ``data:`` URI, or None if absent/unreadable.

    Images are BEST-EFFORT (parity with the former HWPX filler): a missing or
    corrupt globe / chart must leave its anchor blank, never abort the whole
    report. WeasyPrint decodes embedded images at render time and raises on a bad
    one — which would fail the entire PDF — so we fully decode each image with
    Pillow here first (the same library WeasyPrint uses) and drop any that won't
    load. The container is sniffed by magic bytes (globe snapshots arrive as
    JPEG, charts as PNG) so the URI declares the right media type.
    """
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # force a full decode so a truncated image is caught here, not in WeasyPrint
    except Exception:  # noqa: BLE001 - any unreadable image is dropped, never fatal
        logger.warning("dropping unreadable report image (%d bytes)", len(data), exc_info=True)
        return None
    fmt = "jpeg" if data[:3] == b"\xff\xd8\xff" else "png"
    return f"data:image/{fmt};base64," + base64.b64encode(data).decode("ascii")


def _watchlist_rows(payload: DailyReportPayload) -> list[dict[str, object]]:
    """§1 rows: one per country plus the grand-total row (flagged for styling)."""
    rows: list[dict[str, object]] = []
    for entry in payload.watchlist_matrix:
        rows.append(
            {
                "total": False,
                "cells": [
                    country_label(entry.country_code, entry.country_name),
                    entry.leo,
                    entry.meo,
                    entry.geo,
                    entry.heo,
                    entry.total,
                ],
            }
        )
    if payload.watchlist_total is not None:
        t = payload.watchlist_total
        rows.append(
            {
                "total": True,
                "cells": [country_label(t.country_code, t.country_name), t.leo, t.meo, t.geo, t.heo, t.total],
            }
        )
    return rows


def _pass_rows(passes: Sequence[SatellitePass]) -> list[list[str]]:
    """§2/§3 rows: 위성명 | 통과 시점 | 최근접 시각/거리 | 방위/고도 | 비고."""
    rows: list[list[str]] = []
    for p in passes:
        closest, distance = fmt_dt(p.closest_time), fmt_num(p.closest_distance_km)
        closest_cell = f"{closest} / {distance} km" if (closest or distance) else ""
        az, el = fmt_num(p.azimuth_deg, 1), fmt_num(p.elevation_deg, 1)
        az_el = f"{az} / {el}" if (az or el) else ""
        rows.append([p.satellite_name, fmt_dt(p.pass_time), closest_cell, az_el, p.remarks or ""])
    return rows


def _country_blocks(payload: DailyReportPayload, images: ReportImages) -> list[dict[str, object]]:
    """§2/§3 per-country blocks (globe data-URI + pass rows), in report order."""
    activity_by_code = {a.country_code: a for a in payload.country_activity}
    blocks: list[dict[str, object]] = []
    for country, section, default_heading in _COUNTRY_ORDER:
        activity = activity_by_code.get(country.value)
        heading = f"{activity.country_name} 위성 활동 현황" if activity and activity.country_name else default_heading
        passes = activity.passes if activity is not None else []
        blocks.append(
            {
                "section": section,
                "heading": heading,
                "globe": _img_data_uri(images.country_globes.get(country.value)),
                "passes": _pass_rows(passes),
            }
        )
    return blocks


def _conjunction_rows(payload: DailyReportPayload) -> list[list[str]]:
    """§4 rows: 위성명 | 객체명 | 최근접 시각 | 거리 | 충돌 확률 | 위험 구분."""
    return [
        [r.satellite_name, r.object_name, fmt_dt(r.tca), fmt_num(r.distance_km, 3), fmt_prob(r.probability), r.risk_category]
        for r in payload.conjunctions
    ]


def _high_risk_rows(payload: DailyReportPayload) -> list[list[str]]:
    """§5c rows: 국가 | 잔해명 | 위험등급 | RCS | 평균 고도 | 주기 | 근/원지점."""
    return [
        [
            country_label(r.country_code, r.country_name),
            r.debris_name,
            r.risk_grade,
            fmt_rcs(r.rcs_size),
            fmt_num(r.mean_altitude_km),
            fmt_num(r.period_min),
            fmt_apsides(r.perigee_km, r.apogee_km),
        ]
        for r in payload.high_risk_debris
    ]


def build_report_html(payload: DailyReportPayload, prose: ReportProse, images: ReportImages) -> str:
    """Build the report's HTML (PURE — no native deps, fully unit-testable).

    Every section of the report is rendered here; empty sections fall back to a
    "해당 사항 없음" row/note so the document always reads as "no data" rather
    than a blank grid. Text is autoescaped by Jinja; image bytes ride in as
    base64 ``data:`` URIs so the HTML is fully self-contained.
    """
    counts = payload.debris_risk_counts
    context = {
        "title": _REPORT_TITLE,
        "cover_date": f"[ {fmt_cover_date(payload.report_date)} ]",
        "watchlist_headers": _WATCHLIST_HEADERS,
        "watchlist_rows": _watchlist_rows(payload),
        "watchlist_empty": _WATCHLIST_EMPTY_MSG,
        "pass_headers": _PASS_HEADERS,
        "countries": _country_blocks(payload, images),
        "conjunction_headers": _CONJUNCTION_HEADERS,
        "conjunctions": _conjunction_rows(payload),
        "risk_headers": _RISK_COUNT_HEADERS,
        "risk_counts": [counts.critical, counts.high, counts.moderate, counts.low],
        "debris_density": _img_data_uri(images.debris_density),
        "debris_heatmap": _img_data_uri(images.debris_heatmap),
        "high_risk_headers": _HIGH_RISK_HEADERS,
        "high_risk": _high_risk_rows(payload),
        "analysis": [
            {"idx": i, "detail": item.detail, "cause_forecast": item.cause_forecast}
            for i, item in enumerate(prose.analysis_items, start=1)
        ],
        "response_ops": list(prose.response_ops),
        "no_data": _NO_DATA_MSG,
    }
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    return env.from_string(_TEMPLATE).render(**context)


def render_daily_report_pdf(
    payload: DailyReportPayload,
    prose: ReportProse,
    images: ReportImages,
) -> bytes:
    """Render the daily report to PDF bytes (drop-in for the pipeline ``fill_fn``).

    Builds the self-contained HTML via :func:`build_report_html`, then converts
    it with WeasyPrint. WeasyPrint is imported lazily so importing this module
    (and ``tasks``) never requires its native libs — only an actual render does.
    Same call signature as the former HWPX filler: ``(payload, prose, images)``.
    """
    from weasyprint import HTML  # lazy: needs Pango/cairo, present in the engine image

    document = build_report_html(payload, prose, images)
    pdf = HTML(string=document).write_pdf()
    if pdf is None:  # pragma: no cover - WeasyPrint returns bytes when target is None
        raise RuntimeError("WeasyPrint returned no PDF bytes")
    return pdf
