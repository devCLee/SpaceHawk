"""Tests for the HWPX daily-report filler (R6).

The shipped ``assets/daily_report.hwpx`` is fully addressable by table index
(STEP-1 introspection: 10 tables, one blank data row per multi-row table, prose
in top-level section paragraphs), so these tests fill the REAL template and assert
on the re-opened document. Covered:

* multi-row fill (watchlist / 4 country passes / conjunctions / high-risk debris)
  via row cloning — N items render N rows;
* single-value cells (§5a risk counts) filled;
* prose (§6 analysis items + §7 response ops) inserted under the right headings;
* web-supplied images (globes / density / heatmap) embedded; missing images do
  NOT fail;
* [CRITICAL] a structurally wrong template (too few tables / missing data row /
  missing prose heading) -> FillError;
* output bytes re-open as a valid HWPX.
"""

from __future__ import annotations

import base64
import io
import re
import struct
import zipfile
import zlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hwpx import HwpxDocument
from hwpx.tools.table_navigation import _collect_document_tables

from orbital_engine.reports import hwpx_filler
from orbital_engine.reports.hwpx_filler import FillError, fill_daily_report
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

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PK_SIGNATURE = b"PK"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _tiny_png() -> bytes:
    """A minimal but valid 1x1 PNG (no matplotlib dependency in tests)."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _reopen(out: bytes) -> HwpxDocument:
    return HwpxDocument.open(io.BytesIO(out))


def _table_dims(doc: HwpxDocument, index: int) -> tuple[int, int]:
    table = _collect_document_tables(doc)[index].table
    return table.row_count, table.column_count


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def payload() -> DailyReportPayload:
    return DailyReportPayload(
        report_date=date(2026, 6, 22),
        watchlist_matrix=[
            WatchlistRow(
                country_code="US", country_name="미국", leo=10, meo=1, geo=2, heo=0, total=13
            ),
            WatchlistRow(
                country_code="CN", country_name="중국", leo=5, meo=0, geo=3, heo=1, total=9
            ),
        ],
        watchlist_total=WatchlistRow(
            country_code="TOTAL", country_name="합계", leo=15, meo=1, geo=5, heo=1, total=22
        ),
        country_activity=[
            CountryActivity(
                country_code="NK",
                country_name="북한",
                passes=[
                    SatellitePass(
                        satellite_name="KMS-4",
                        satellite_id="41332",
                        pass_time=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                        closest_time=datetime(2026, 6, 22, 3, 16, tzinfo=UTC),
                        closest_distance_km=412.5,
                        azimuth_deg=128.0,
                        elevation_deg=42.0,
                        remarks="첫 통과",
                    ),
                    SatellitePass(
                        satellite_name="KMS-3",
                        satellite_id="39026",
                        pass_time=datetime(2026, 6, 22, 14, 2, tzinfo=UTC),
                    ),
                ],
            ),
            CountryActivity(
                country_code="CN",
                country_name="중국",
                passes=[
                    SatellitePass(
                        satellite_name="YAOGAN-30",
                        satellite_id="43000",
                        pass_time=datetime(2026, 6, 22, 5, 0, tzinfo=UTC),
                    )
                ],
            ),
        ],
        conjunctions=[
            ConjunctionRow(
                satellite_name="KOMPSAT-5",
                object_name="DEBRIS-9",
                tca=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                distance_km=0.842,
                probability=1e-4,
                risk_category="높음",
            ),
            ConjunctionRow(
                satellite_name="ARIRANG",
                object_name="ROCKET BODY",
                tca=datetime(2026, 6, 22, 9, 0, tzinfo=UTC),
                distance_km=5.0,
                probability=1e-6,
                risk_category="낮음",
            ),
        ],
        debris_risk_counts=DebrisRiskCounts(critical=2, high=7, moderate=15, low=120),
        high_risk_debris=[
            HighRiskDebrisRow(
                country_code="CIS",
                country_name="러시아",
                debris_name="COSMOS 1408 DEB",
                risk_grade="심각",
                rcs_size="LARGE",
                mean_altitude_km=480.0,
                period_min=94.2,
                perigee_km=460.0,
                apogee_km=500.0,
            ),
            HighRiskDebrisRow(
                country_code="PRC",
                country_name="중국",
                debris_name="FENGYUN 1C DEB",
                risk_grade="높음",
                rcs_size=0.5,
                mean_altitude_km=860.0,
                period_min=102.0,
                perigee_km=850.0,
                apogee_km=870.0,
            ),
        ],
    )


@pytest.fixture
def prose() -> ReportProse:
    return ReportProse(
        analysis_items=[
            AnalysisItem(
                detail="북한 정찰위성 통과 식별.",
                cause_forecast="궤도 유지 기동 없음, 추가 통과 예상.",
            ),
            AnalysisItem(
                detail="고위험 잔해 1건 근접.",
                cause_forecast="자연 감쇠로 위험 감소 예상.",
            ),
        ],
        response_ops=[
            "추적 레이더 자산 우선 배정.",
            "근접 위성 운용사 통보.",
        ],
    )


@pytest.fixture
def images() -> ReportImages:
    png = _tiny_png()
    return ReportImages(
        country_globes={"NK": png, "CN": png, "RU": png, "JP": png},
        debris_density=png,
        debris_heatmap=png,
    )


# --------------------------------------------------------------------------- #
# happy path — valid output
# --------------------------------------------------------------------------- #


def test_fill_returns_valid_hwpx_bytes(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)

    assert isinstance(out, bytes)
    assert out.startswith(PK_SIGNATURE)  # HWPX is a zip
    assert len(out) > len(PK_SIGNATURE)


def test_output_reopens_as_valid_hwpx(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)

    assert _reopen(out).validate().ok


# --------------------------------------------------------------------------- #
# multi-row tables (row cloning — N items render N rows)
# --------------------------------------------------------------------------- #


def test_watchlist_rows_cloned_and_filled(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._WATCHLIST_TABLE].table

    # header (1) + 2 country rows + 1 total row = 4
    assert table.row_count == 4
    assert [table.cell(1, c).text for c in range(6)] == ["미국", "10", "1", "2", "0", "13"]
    assert [table.cell(2, c).text for c in range(6)] == ["중국", "5", "0", "3", "1", "9"]
    assert [table.cell(3, c).text for c in range(6)] == ["합계", "15", "1", "5", "1", "22"]


def test_country_pass_rows_cloned(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)

    nk_index = hwpx_filler._COUNTRY_TABLES[hwpx_filler.ReportCountry.NORTH_KOREA]
    nk = _collect_document_tables(doc)[nk_index].table
    # title(0) + image(1) + col-headers(2) + 2 pass rows = 5
    assert nk.row_count == 5
    # 위성명 is the new FIRST column (G4): header present, data filled.
    assert nk.column_count == 5
    assert nk.cell(hwpx_filler._COUNTRY_DATA_ROW - 1, 0).text == "위성명"
    text = doc.export_text()
    assert "2026-06-22 03:14Z" in text
    assert "412.50 km" in text
    assert "첫 통과" in text


def test_country_pass_satellite_name_in_col0(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)

    nk_index = hwpx_filler._COUNTRY_TABLES[hwpx_filler.ReportCountry.NORTH_KOREA]
    nk = _collect_document_tables(doc)[nk_index].table
    data0 = hwpx_filler._COUNTRY_DATA_ROW
    # Two NK passes -> two data rows, each with its satellite_name in column 0
    # and pass_time shifted to column 1.
    assert nk.cell(data0, 0).text == "KMS-4"
    assert nk.cell(data0, 1).text == "2026-06-22 03:14Z"
    assert nk.cell(data0 + 1, 0).text == "KMS-3"
    assert nk.cell(data0 + 1, 1).text == "2026-06-22 14:02Z"

    # Single-pass country: China's one pass -> one data row.
    cn_index = hwpx_filler._COUNTRY_TABLES[hwpx_filler.ReportCountry.CHINA]
    cn = _collect_document_tables(doc)[cn_index].table
    assert cn.cell(data0, 0).text == "YAOGAN-30"


def test_conjunction_rows_filled(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._CONJUNCTION_TABLE].table

    assert table.row_count == 3  # header + 2 rows
    assert [table.cell(1, c).text for c in range(6)] == [
        "KOMPSAT-5",
        "DEBRIS-9",
        "2026-06-22 03:14Z",
        "0.842",
        "1.00e-04",
        "높음",
    ]


def test_high_risk_debris_rows_filled(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._HIGH_RISK_TABLE].table

    assert table.row_count == 3  # header + 2 rows
    assert [table.cell(1, c).text for c in range(7)] == [
        "러시아",
        "COSMOS 1408 DEB",
        "심각",
        "LARGE",
        "480.00",
        "94.20",
        "460.00/500.00",
    ]


# --------------------------------------------------------------------------- #
# single-value cells (§5a risk counts)
# --------------------------------------------------------------------------- #


def test_risk_counts_filled(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._RISK_COUNT_TABLE].table

    assert [table.cell(1, c).text for c in range(4)] == ["2", "7", "15", "120"]


# --------------------------------------------------------------------------- #
# prose (§6 / §7)
# --------------------------------------------------------------------------- #


def test_prose_inserted(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    text = _reopen(out).export_text()

    assert "상세 분석 내용: 북한 정찰위성 통과 식별." in text
    assert "원인 및 예상 분석: 궤도 유지 기동 없음, 추가 통과 예상." in text
    assert "추적 레이더 자산 우선 배정." in text
    assert "근접 위성 운용사 통보." in text


# --------------------------------------------------------------------------- #
# cover date (table[0]) — dynamic from payload.report_date
# --------------------------------------------------------------------------- #


def _cover_text(doc: HwpxDocument) -> str:
    return _collect_document_tables(doc)[hwpx_filler._COVER_TABLE].table.cell(0, 0).text


def test_cover_date_is_dynamic(payload, prose, images) -> None:
    # payload.report_date is 2026-06-22, which is a Monday -> 월.
    out = fill_daily_report(payload, prose, images)
    text = _cover_text(_reopen(out))

    assert "2026. 06. 22. (월)" in text
    # The stale template weekday (화) must be gone.
    assert "(화)" not in text
    # Title prefix is preserved untouched.
    assert "[SpaceHawk] 일일 우주작전현황 보고" in text


def test_cover_weekday_mapping(prose, images) -> None:
    # 2026-06-24 is a Wednesday -> 수 (verifies the weekday map, not just one date).
    payload = DailyReportPayload(report_date=date(2026, 6, 24))
    out = fill_daily_report(payload, prose, images)
    text = _cover_text(_reopen(out))

    assert "2026. 06. 24. (수)" in text
    assert "[SpaceHawk] 일일 우주작전현황 보고" in text


def test_cover_missing_date_does_not_fail(payload, prose, images, tmp_path) -> None:
    # Strip the cover date paragraph text: cover fill must warn, not raise.
    doc = HwpxDocument.open(io.BytesIO(hwpx_filler._load_default_template()))
    cover = _collect_document_tables(doc)[hwpx_filler._COVER_TABLE].table
    for para in cover.cell(0, 0).paragraphs:
        if hwpx_filler._COVER_DATE_RE.search(para.text or ""):
            para.clear_text()
    path = tmp_path / "no_cover_date.hwpx"
    path.write_bytes(doc.to_bytes())

    out = fill_daily_report(payload, prose, images, template_path=str(path))
    assert _reopen(out).validate().ok


# --------------------------------------------------------------------------- #
# images
# --------------------------------------------------------------------------- #


def test_all_images_embedded(payload, prose, images) -> None:
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)

    # 4 globes + density + heatmap = 6 images.
    embedded = doc.list_images()
    assert len(embedded) == 6
    assert all(img["Format"] == "png" for img in embedded)


def test_missing_images_do_not_fail(payload, prose) -> None:
    # No images supplied -> still a valid report; every anchor gets a fallback
    # PNG so no anchor is left holding the template's placeholder prose.
    out = fill_daily_report(payload, prose, ReportImages())
    doc = _reopen(out)

    assert doc.validate().ok
    # 4 globe anchors + density + heatmap all filled with fallback graphics.
    assert len(doc.list_images()) == 6


def test_partial_images_embed_supplied_plus_fallback(payload, prose) -> None:
    # One real globe + one real heatmap supplied; the 3 other globes and the
    # density anchor get fallback PNGs -> every anchor (6) ends up with a picture.
    png = _tiny_png()
    partial = ReportImages(country_globes={"NK": png}, debris_heatmap=png)
    out = fill_daily_report(payload, prose, partial)
    doc = _reopen(out)

    assert len(doc.list_images()) == 6


def test_globe_placeholder_text_cleared(payload, prose) -> None:
    # The template's globe anchor cell ships literal placeholder prose. Embedding a
    # globe must wipe it so the image is not left sitting beside stray text.
    png = _tiny_png()
    out = fill_daily_report(payload, prose, ReportImages(country_globes={"NK": png}))
    doc = _reopen(out)

    nk_index = hwpx_filler._COUNTRY_TABLES[hwpx_filler.ReportCountry.NORTH_KOREA]
    nk = _collect_document_tables(doc)[nk_index].table
    row, col = hwpx_filler._COUNTRY_IMAGE_CELL
    assert "This is where" not in nk.cell(row, col).text


def test_missing_globe_uses_fallback_and_clears_text(payload, prose) -> None:
    # No globe for any country and no heatmap -> each anchor gets a fallback image
    # and none retains the placeholder prose.
    out = fill_daily_report(payload, prose, ReportImages())
    doc = _reopen(out)

    assert len(doc.list_images()) == 6  # every anchor filled (real or fallback)
    row, col = hwpx_filler._COUNTRY_IMAGE_CELL
    for country, ti in hwpx_filler._COUNTRY_TABLES.items():
        cell = _collect_document_tables(doc)[ti].table.cell(row, col)
        assert "This is where" not in cell.text, country.value


# --------------------------------------------------------------------------- #
# empty payload still produces a valid report (every section empty-capable)
# --------------------------------------------------------------------------- #


def test_empty_payload_fills_validly(prose, images) -> None:
    empty = DailyReportPayload(report_date=date(2026, 6, 22))
    out = fill_daily_report(empty, prose, images)
    doc = _reopen(out)

    assert doc.validate().ok
    # The blank single data rows are left untouched (no clone needed).
    assert _table_dims(doc, hwpx_filler._WATCHLIST_TABLE)[0] == 2
    # Risk counts default to zero and are still written.
    risk = _collect_document_tables(doc)[hwpx_filler._RISK_COUNT_TABLE].table
    assert [risk.cell(1, c).text for c in range(4)] == ["0", "0", "0", "0"]


# --------------------------------------------------------------------------- #
# §1 관심 목록 — empty-vs-populated message
# --------------------------------------------------------------------------- #


def test_watchlist_empty_shows_message(prose, images) -> None:
    # No watchlist satellites -> §1 data row carries the empty message in cell 0,
    # the remaining count cells cleared (not a zero grid).
    empty = DailyReportPayload(report_date=date(2026, 6, 22))
    out = fill_daily_report(empty, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._WATCHLIST_TABLE].table

    assert table.row_count == 2  # header + single (unexpanded) data row
    assert table.cell(1, 0).text == hwpx_filler._WATCHLIST_EMPTY_MSG
    assert [table.cell(1, c).text for c in range(1, 6)] == ["", "", "", "", ""]


def test_watchlist_nonempty_still_renders_rows(payload, prose, images) -> None:
    # Populated matrix keeps the per-country (+ total) rows and shows no message.
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    table = _collect_document_tables(doc)[hwpx_filler._WATCHLIST_TABLE].table

    assert table.row_count == 4  # header + 2 country rows + total
    assert table.cell(1, 0).text == "미국"
    assert hwpx_filler._WATCHLIST_EMPTY_MSG not in doc.export_text()


# --------------------------------------------------------------------------- #
# failure policy (CRITICAL) — fail closed on a structurally wrong template
# --------------------------------------------------------------------------- #


def test_too_few_tables_raises(payload, prose, images, tmp_path) -> None:
    # A document with no report tables can never hold the data -> FillError.
    doc = HwpxDocument.new()
    doc.add_table(2, 2)
    path = tmp_path / "too_few.hwpx"
    path.write_bytes(doc.to_bytes())

    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, images, template_path=str(path))
    assert "too few tables" in str(exc.value)


def test_missing_prose_heading_raises(payload, prose, images, tmp_path) -> None:
    # Take the real template (data tables intact) but strip the §6 heading text so
    # only the prose insert can fail -> fail-closed on the missing heading.
    doc = HwpxDocument.open(io.BytesIO(hwpx_filler._load_default_template()))
    for para in doc.paragraphs:
        if (para.text or "").strip().endswith(hwpx_filler._ANALYSIS_HEADING):
            para.clear_text()
    path = tmp_path / "no_heading.hwpx"
    path.write_bytes(doc.to_bytes())

    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, images, template_path=str(path))
    assert hwpx_filler._ANALYSIS_HEADING in str(exc.value)


def test_data_cell_out_of_range_raises(payload, prose, images, tmp_path) -> None:
    # Ten tables but the watchlist table is too narrow for its 6 columns ->
    # a data-cell write is out of range and must fail closed.
    doc = HwpxDocument.new()
    for _ in range(hwpx_filler._MIN_TABLES):
        doc.add_table(2, 2)  # only 2 columns, watchlist needs 6
    path = tmp_path / "narrow.hwpx"
    path.write_bytes(doc.to_bytes())

    with pytest.raises(FillError):
        fill_daily_report(payload, prose, images, template_path=str(path))


def test_fill_error_lists_offending_slots() -> None:
    err = FillError("structure mismatch", slots=["a", "b"])
    assert err.slots == ["a", "b"]
    assert "a" in str(err) and "b" in str(err)


# --------------------------------------------------------------------------- #
# default-asset path (the bundled real template fills end-to-end)
# --------------------------------------------------------------------------- #


def test_default_template_loads_via_resources() -> None:
    data = hwpx_filler._load_default_template()
    assert data.startswith(PK_SIGNATURE)


def test_default_template_fills_end_to_end(payload, prose, images) -> None:
    # The shipped daily_report.hwpx is fillable via index addressing (no labels).
    out = fill_daily_report(payload, prose, images)
    assert _reopen(out).validate().ok


def test_image_format_sniffs_jpeg_vs_png() -> None:
    # Globe snapshots arrive as JPEG (small); charts as PNG. The embedder must
    # label each correctly for add_image rather than assume PNG.
    assert hwpx_filler._image_format(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "jpg"
    assert hwpx_filler._image_format(b"\x89PNG\r\n\x1a\n") == "png"
    assert hwpx_filler._image_format(b"") == "png"  # unknown/empty -> png default


def test_default_template_embeds_jpeg_globe(payload, prose) -> None:
    # A JPEG globe (sniffed -> jpg) embeds without error and lands in the doc.
    jpeg_1x1 = base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB/8AACwgAAQABAQERAP/EABQAAQAAAAAA"
        "AAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/AT//2Q=="
    )
    assert jpeg_1x1[:3] == b"\xff\xd8\xff"
    images = ReportImages(country_globes={"NK": jpeg_1x1})
    out = fill_daily_report(payload, prose, images)
    doc = _reopen(out)
    assert doc.validate().ok
    assert len(doc.list_images()) >= 1


# Known-good Hancom-loadable HWPX (hwpxlib reader_writer/SimplePicture.hwpx).
# It is the GROUND TRUTH for how an embedded image must be wired: a golden-diff
# against it (not guesswork) showed the broken-image icon comes from a missing
# isEmbeded flag on the content.hpf <opf:item> that binaryItemIDRef resolves to —
# NOT from the header binItem id, and NOT from META-INF/manifest.xml (golden
# ships that empty). See hwpx_filler._mark_bindata_embedded.
_GOLDEN_HWPX = Path(__file__).parent / "fixtures" / "SimplePicture.hwpx"


def _assert_embedded_image_contract(data: bytes) -> int:
    """Assert the embedded-image resolution chain Hancom needs to render a picture.

    Verified against the golden ``SimplePicture.hwpx``::

        section  <hc:img binaryItemIDRef="X">
          └─► content.hpf  <opf:item id="X" href="BinData/.." isEmbeded="1"/>
                └─► BinData/.. part present in the package
        META-INF/manifest.xml carries NO <file-entry> (golden ships it empty)

    A dangling ref, a missing ``isEmbeded`` flag, or an absent BinData part each
    makes Hancom show a broken-image icon. Returns the count of resolved refs.
    """
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    hpf = z.read("Contents/content.hpf").decode("utf-8")
    opf: dict[str, tuple[str, bool]] = {}
    for tag in re.findall(r"<opf:item\b[^>]*?/>", hpf):
        id_match = re.search(r'\bid="([^"]*)"', tag)
        href_match = re.search(r'\bhref="([^"]*)"', tag)
        if id_match and href_match:
            opf[id_match.group(1)] = (href_match.group(1), 'isEmbeded="1"' in tag)

    refs: list[str] = []
    for name in names:
        if re.match(r"Contents/section\d+\.xml", name):
            section = z.read(name).decode("utf-8")
            refs += re.findall(r'<hc:img\b[^>]*?\bbinaryItemIDRef="([^"]*)"', section)
    assert refs, "expected at least one embedded <hc:img>"

    for ref in refs:
        assert ref in opf, f"binaryItemIDRef {ref!r} has no content.hpf <opf:item id>"
        href, embedded = opf[ref]
        assert embedded, f'opf:item {ref!r} missing isEmbeded="1" -> Hancom broken-image icon'
        assert href.startswith("BinData/"), f"opf:item {ref!r} href not a BinData part: {href}"
        assert href in names, f"BinData part {href!r} referenced but absent from package"

    manifest = z.read("META-INF/manifest.xml").decode("utf-8") if "META-INF/manifest.xml" in names else ""
    assert "file-entry" not in manifest, "manifest must stay empty (golden ships no file-entry)"
    return len(refs)


def test_golden_fixture_satisfies_image_contract() -> None:
    # Ground truth: pin the embedded-image resolution chain against a known-good
    # Hancom-loadable HWPX. If this fails, the contract itself moved — re-derive
    # _assert_embedded_image_contract against a fresh golden file before touching
    # the filler. This is what makes the regression test below trustworthy.
    assert _GOLDEN_HWPX.exists(), f"golden fixture missing: {_GOLDEN_HWPX}"
    assert _assert_embedded_image_contract(_GOLDEN_HWPX.read_bytes()) >= 1


def test_embedded_images_resolve_via_opf_isembeded(payload, prose, images) -> None:
    # REGRESSION (broken-image loop): python-hwpx add_image registers BinData in
    # content.hpf + header binDataList + the section <hc:img> ref, but OMITS
    # Hancom's isEmbeded flag, so every embedded picture renders as a broken-image
    # icon even though the bytes, the binaryItemIDRef, and the BinData part are all
    # intact. fill_daily_report patches content.hpf so our output satisfies the
    # SAME embedded-image contract the golden SimplePicture.hwpx does (asserted in
    # test_golden_fixture_satisfies_image_contract).
    out = fill_daily_report(payload, prose, images)
    assert _assert_embedded_image_contract(out) >= 1
    # still a valid, re-openable HWPX after the content.hpf patch
    assert _reopen(out).validate().ok
