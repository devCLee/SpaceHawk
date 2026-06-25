"""Tests for the PDF report renderer.

The renderer is split so coverage does not depend on WeasyPrint's native libs:

* :func:`build_report_html` holds ALL layout logic and is PURE — every section,
  empty-state, escaping, and image-embedding assertion runs here on any host.
* :func:`render_daily_report_pdf` is the thin HTML→PDF step; its one test is
  guarded by ``importorskip("weasyprint")`` so a dev box without Pango/cairo
  skips it while the engine container (and CI) runs it.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from orbital_engine.reports.pdf_renderer import (
    _img_data_uri,
    build_report_html,
    render_daily_report_pdf,
)
from orbital_engine.reports.schemas import (
    AnalysisItem,
    ConjunctionRow,
    CountryActivity,
    DailyReportPayload,
    DebrisRiskCounts,
    HighRiskDebrisRow,
    ReportImages,
    ReportProse,
    SatellitePass,
    WatchlistRow,
)
from orbital_engine.reports.validate import ReportValidationError, validate_pdf


# Small but FULLY VALID PNG / JPEG (built with Pillow), so they survive the
# renderer's decode-validation the way real globe/chart bytes do.
def _img_bytes(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 60, 60)).save(buf, format=fmt)
    return buf.getvalue()


_PNG = _img_bytes("PNG")
_JPEG = _img_bytes("JPEG")


def _payload() -> DailyReportPayload:
    return DailyReportPayload(
        report_date=datetime(2026, 6, 24, tzinfo=UTC).date(),
        watchlist_matrix=[
            WatchlistRow(country_code="NK", country_name="북한", leo=3, meo=0, geo=1, heo=0, total=4),
        ],
        watchlist_total=WatchlistRow(
            country_code="TOTAL", country_name="합계", leo=3, meo=0, geo=1, heo=0, total=4
        ),
        country_activity=[
            CountryActivity(
                country_code="NK",
                country_name="북한",
                passes=[
                    SatellitePass(
                        satellite_name="KMS-4",
                        satellite_id="41332",
                        pass_time=datetime(2026, 6, 24, 1, 23, tzinfo=UTC),
                        closest_time=datetime(2026, 6, 24, 1, 25, tzinfo=UTC),
                        closest_distance_km=512.3,
                        azimuth_deg=145.0,
                        elevation_deg=37.5,
                        remarks="정상",
                    )
                ],
            )
        ],
        conjunctions=[
            ConjunctionRow(
                satellite_name="KOMPSAT-5",
                object_name="DEBRIS-X",
                tca=datetime(2026, 6, 24, 6, 0, tzinfo=UTC),
                distance_km=1.234,
                probability=2.5e-4,
                risk_category="높음",
            )
        ],
        debris_risk_counts=DebrisRiskCounts(critical=1, high=2, moderate=3, low=4),
        high_risk_debris=[
            HighRiskDebrisRow(
                country_code="CN",
                country_name="중국",
                debris_name="CZ-3B DEB",
                risk_grade="심각",
                rcs_size="LARGE",
                mean_altitude_km=780.0,
                period_min=100.5,
                perigee_km=760.0,
                apogee_km=800.0,
            )
        ],
    )


def _prose() -> ReportProse:
    return ReportProse(
        analysis_items=[AnalysisItem(detail="북한 위성 통과 1건.", cause_forecast="추가 기동 가능성 낮음.")],
        response_ops=["관심목록 위성 추적 유지", "근접 객체 재평가"],
    )


def _images() -> ReportImages:
    return ReportImages(country_globes={"NK": _JPEG}, debris_density=_PNG, debris_heatmap=_PNG)


# --------------------------------------------------------------------------- #
# build_report_html (PURE — no WeasyPrint)
# --------------------------------------------------------------------------- #


def test_html_has_title_and_cover_date() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    assert "일일 우주작전현황 보고" in html
    # 2026-06-24 is a Wednesday → (수); rendered Korean-style inside brackets.
    assert "[ 2026. 06. 24. (수) ]" in html


def test_html_renders_watchlist_rows_and_total() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    assert "북한" in html
    assert "관심목록 등록 위성 현황" in html
    # the total row carries the styling hook
    assert 'class="total"' in html
    assert "합계" in html


def test_html_watchlist_empty_shows_message() -> None:
    payload = _payload().model_copy(update={"watchlist_matrix": [], "watchlist_total": None})
    html = build_report_html(payload, _prose(), _images())
    assert "등록된 관심 목록 위성 데이터가 없습니다." in html


def test_html_country_globe_embedded_as_data_uri() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    # globe was a JPEG -> data:image/jpeg URI present, placeholder absent for NK
    assert "data:image/jpeg;base64," in html
    assert "KMS-4" in html  # pass row rendered


def test_html_missing_globe_shows_placeholder() -> None:
    images = ReportImages(country_globes={}, debris_density=_PNG, debris_heatmap=_PNG)
    html = build_report_html(_payload(), _prose(), images)
    assert "위성 위치 스냅샷 없음" in html


def test_html_renders_conjunctions_and_risk_counts() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    assert "DEBRIS-X" in html
    assert "2.50e-04" in html  # probability formatted
    # risk counts row 심각/높음/보통/낮음 = 1/2/3/4
    for n in ("1", "2", "3", "4"):
        assert f"<td>{n}</td>" in html


def test_html_renders_debris_images_and_high_risk_rows() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    assert "고도별 잔해 밀도" in html
    assert "2D 잔해 밀도 히트맵" in html
    assert "data:image/png;base64," in html  # the two debris charts
    assert "CZ-3B DEB" in html
    assert "760.00/800.00" in html  # apsides perigee/apogee


def test_html_missing_debris_images_show_placeholders() -> None:
    images = ReportImages(country_globes={"NK": _JPEG})
    html = build_report_html(_payload(), _prose(), images)
    assert "밀도 차트 없음" in html
    assert "히트맵 없음" in html


def test_html_renders_prose_and_response_ops() -> None:
    html = build_report_html(_payload(), _prose(), _images())
    assert "북한 위성 통과 1건." in html
    assert "추가 기동 가능성 낮음." in html
    assert "관심목록 위성 추적 유지" in html
    assert "<ol class=\"ops\">" in html


def test_html_empty_prose_shows_no_data() -> None:
    html = build_report_html(_payload(), ReportProse(), _images())
    # both §6 and §7 fall back to the no-data note
    assert html.count("해당 사항 없음") >= 2


def test_html_escapes_untrusted_text() -> None:
    # A satellite name with HTML must be escaped, never injected as live markup.
    payload = _payload()
    payload.country_activity[0].passes[0].satellite_name = "<script>x</script>"
    html = build_report_html(payload, _prose(), _images())
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_img_data_uri_sniffs_jpeg_and_png() -> None:
    assert _img_data_uri(_JPEG).startswith("data:image/jpeg;base64,")
    assert _img_data_uri(_PNG).startswith("data:image/png;base64,")
    assert _img_data_uri(None) is None
    assert _img_data_uri(b"") is None


def test_img_data_uri_drops_unreadable_bytes() -> None:
    # Best-effort: a corrupt/truncated image must be dropped (None), never raise —
    # otherwise WeasyPrint would abort the whole report on one bad globe.
    assert _img_data_uri(b"\xff\xd8\xff broken jpeg bytes") is None
    assert _img_data_uri(b"\x89PNG\r\n\x1a\n truncated") is None
    assert _img_data_uri(b"not an image at all") is None


def test_html_drops_unreadable_globe_to_placeholder() -> None:
    # A corrupt globe leaves its anchor as the placeholder note, not a data URI,
    # and the rest of the report still builds.
    images = ReportImages(
        country_globes={"NK": b"\xff\xd8\xff broken"}, debris_density=_PNG, debris_heatmap=_PNG
    )
    html = build_report_html(_payload(), _prose(), images)
    assert "위성 위치 스냅샷 없음" in html  # corrupt globe -> placeholder, not a data URI
    assert "일일 우주작전현황 보고" in html  # report still builds
    assert "data:image/png;base64," in html  # the valid debris charts still embed


# --------------------------------------------------------------------------- #
# render_daily_report_pdf (needs WeasyPrint native libs)
# --------------------------------------------------------------------------- #


def test_render_produces_valid_pdf(weasyprint_runtime: None) -> None:
    data = render_daily_report_pdf(_payload(), _prose(), _images())
    assert data.startswith(b"%PDF-")
    validate_pdf(data)  # passes the discard-or-ship gate


def test_render_empty_payload_still_valid_pdf(weasyprint_runtime: None) -> None:
    payload = DailyReportPayload(report_date=datetime(2026, 6, 24, tzinfo=UTC).date())
    data = render_daily_report_pdf(payload, ReportProse(), ReportImages())
    assert data.startswith(b"%PDF-")
    validate_pdf(data)


def test_validate_pdf_accepts_real_pdf() -> None:
    # Exercise the pypdf parse path cross-platform (no WeasyPrint needed): a real
    # one-page PDF built with pypdf must pass the gate. This covers the parser
    # branch that the garbage-input tests skip via the early size check.
    import io as _io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = _io.BytesIO()
    writer.write(buf)
    validate_pdf(buf.getvalue())  # raises on any defect


def test_validate_pdf_rejects_non_pdf() -> None:
    with pytest.raises(ReportValidationError):
        validate_pdf(b"not a pdf at all")


def test_validate_pdf_rejects_headered_garbage() -> None:
    # Right magic + big enough to pass the cheap pre-checks, but unparseable —
    # the pypdf parse branch must reject it (this is the path that caught a wrong
    # exception-class import that the small-garbage test could not reach).
    with pytest.raises(ReportValidationError):
        validate_pdf(b"%PDF-1.4\n" + b"junk-not-a-real-pdf " * 32)
