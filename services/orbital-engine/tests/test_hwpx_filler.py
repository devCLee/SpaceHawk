"""Tests for the HWPX template filler (T5).

The shipped ``daily_report.hwpx`` lacks the unique anchor labels the filler needs
(its tables repeat column headers and leave data cells blank), so these tests
build a SYNTHETIC template in-process with :meth:`HwpxDocument.new` + ``add_table``
carrying exactly the labels :data:`hwpx_filler.SLOTMAP` expects. That exercises
the full fill + embed + raise-on-failure logic against a real OWPML document.

Covered:
* happy path → valid HWPX bytes (PK zip header), every slot applied;
* the returned bytes re-open as a valid HWPX (round-trip + ``validate().ok``);
* a chart embed actually lands an image in the document;
* an unknown / missing text slot → :class:`FillError` (never a silent pass);
* a missing chart PNG and an ambiguous/absent anchor → :class:`FillError`.
"""

from __future__ import annotations

import io
import struct
import zlib
from datetime import UTC, date, datetime

import pytest
from hwpx import HwpxDocument

from orbital_engine.reports import hwpx_filler
from orbital_engine.reports.hwpx_filler import (
    SLOTMAP,
    ChartSlot,
    FillError,
    SlotMap,
    fill_daily_report,
)
from orbital_engine.reports.schemas import (
    ConjunctionRow,
    CountryBreakdownEntry,
    DailyReportPayload,
    SurveillanceCategoryCount,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PK_SIGNATURE = b"PK"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _tiny_png() -> bytes:
    """A minimal but valid 1x1 PNG (sidesteps a matplotlib dependency in tests)."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _synthetic_template() -> bytes:
    """Build an OWPML template whose cells carry the slotmap's unique labels.

    Layout: a 2-row table per slot family. Text anchors put the label in the cell
    left of / above the value cell; chart anchors put the label above an empty
    cell that will hold the picture. Every label here is globally unique, so
    ``fill_by_path`` / ``find_cell_by_label`` resolve to exactly one cell.
    """
    doc = HwpxDocument.new()

    # Text slots reachable by "<label> > right": label in col0, value in col1.
    right_labels = [
        "보고일자",
        "감시위성 합계",
        "최우선 근접 위성",
        "최우선 근접 거리",
        "최다 보유국",
    ]
    for label in right_labels:
        table = doc.add_table(1, 2)
        table.set_cell_text(0, 0, label, logical=True)

    # Prose slots reachable by "<label> > down": label in row0, body in row1.
    for label in ["개요 본문", "분석내용 본문", "향후추진 본문"]:
        table = doc.add_table(2, 1)
        table.set_cell_text(0, 0, label, logical=True)

    # Chart anchors reachable by "<label> > down": label in row0, image in row1.
    for slot in SLOTMAP.charts:
        table = doc.add_table(2, 1)
        table.set_cell_text(0, 0, slot.label, logical=True)

    return doc.to_bytes()


@pytest.fixture
def template_path(tmp_path) -> str:
    path = tmp_path / "synthetic_template.hwpx"
    path.write_bytes(_synthetic_template())
    return str(path)


@pytest.fixture
def payload() -> DailyReportPayload:
    return DailyReportPayload(
        report_date=date(2026, 6, 22),
        surveillance_categories=[
            SurveillanceCategoryCount(category="recon", count=7),
            SurveillanceCategoryCount(category="comms", count=5),
        ],
        conjunctions=[
            ConjunctionRow(
                conjunction_id="CDM-1",
                primary_object_id="OBJ-A",
                primary_name="KOMPSAT-5",
                secondary_object_id="OBJ-B",
                secondary_name="DEBRIS-9",
                miss_distance_km=0.842,
                probability=1e-4,
                tca=datetime(2026, 6, 22, 3, 14, tzinfo=UTC),
                alert_level="HIGH",
            ),
            ConjunctionRow(
                conjunction_id="CDM-2",
                primary_object_id="OBJ-C",
                primary_name="ARIRANG",
                secondary_object_id="OBJ-D",
                secondary_name="ROCKET BODY",
                miss_distance_km=5.0,
                probability=1e-6,
                tca=datetime(2026, 6, 22, 9, 0, tzinfo=UTC),
                alert_level="LOW",
            ),
        ],
        country_breakdown=[
            CountryBreakdownEntry(owner_code="US", owner_name="미국", count=120),
            CountryBreakdownEntry(owner_code="PRC", owner_name="중국", count=90),
        ],
    )


@pytest.fixture
def prose() -> dict[str, str]:
    return {
        "개요": "오늘의 우주 상황 개요.",
        "분석내용": "근접 위험 분석 내용.",
        "향후추진": "향후 추진 계획.",
    }


@pytest.fixture
def charts() -> dict[str, bytes]:
    png = _tiny_png()
    return {slot.chart_key: png for slot in SLOTMAP.charts}


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #


def test_fill_returns_valid_hwpx_bytes(template_path, payload, prose, charts) -> None:
    out = fill_daily_report(payload, prose, charts, template_path=template_path)

    assert isinstance(out, bytes)
    assert out.startswith(PK_SIGNATURE)  # HWPX is a zip
    assert len(out) > len(PK_SIGNATURE)


def test_output_reopens_as_valid_hwpx(template_path, payload, prose, charts) -> None:
    out = fill_daily_report(payload, prose, charts, template_path=template_path)

    reopened = HwpxDocument.open(io.BytesIO(out))
    assert reopened.validate().ok


def test_text_slots_actually_filled(template_path, payload, prose, charts) -> None:
    out = fill_daily_report(payload, prose, charts, template_path=template_path)
    text = HwpxDocument.open(io.BytesIO(out)).export_text()

    # report_date formatted, the most-severe conjunction (0.842 km), the leader.
    assert "2026. 06. 22." in text
    assert "12" in text  # surveillance total 7 + 5
    assert "KOMPSAT-5 / DEBRIS-9" in text
    assert "0.842" in text
    assert "미국" in text
    assert "오늘의 우주 상황 개요." in text


def test_charts_embedded_into_document(template_path, payload, prose, charts) -> None:
    out = fill_daily_report(payload, prose, charts, template_path=template_path)
    reopened = HwpxDocument.open(io.BytesIO(out))

    images = reopened.list_images()
    assert len(images) == len(SLOTMAP.charts)
    assert all(img["Format"] == "png" for img in images)


def test_empty_sections_fill_with_placeholder(template_path, prose, charts) -> None:
    empty = DailyReportPayload(report_date=date(2026, 6, 22))
    out = fill_daily_report(empty, prose, charts, template_path=template_path)
    text = HwpxDocument.open(io.BytesIO(out)).export_text()

    assert "0" in text  # surveillance total
    assert "정보 없음" in text  # no conjunctions / no country breakdown


# --------------------------------------------------------------------------- #
# failure policy (CRITICAL) — never ship a half-filled report
# --------------------------------------------------------------------------- #


def test_missing_text_label_raises(template_path, payload, prose, charts) -> None:
    bad = SlotMap(
        text_paths={**SLOTMAP.text_paths, "phantom": "존재하지 않는 라벨 > right"},
        charts=SLOTMAP.charts,
    )
    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, charts, template_path=template_path, slotmap=bad)
    assert "phantom" in str(exc.value)


def test_ambiguous_text_label_raises(payload, prose, charts, tmp_path) -> None:
    # Two cells with the same label make fill_by_path refuse ("ambiguous label").
    doc = HwpxDocument.new()
    for _ in range(2):
        table = doc.add_table(1, 2)
        table.set_cell_text(0, 0, "보고일자", logical=True)
    path = tmp_path / "ambiguous.hwpx"
    path.write_bytes(doc.to_bytes())

    only_date = SlotMap(text_paths={"report_date": "보고일자 > right"}, charts=())
    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, charts, template_path=str(path), slotmap=only_date)
    assert "report_date" in str(exc.value)


def test_missing_chart_png_raises(template_path, payload, prose) -> None:
    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, {}, template_path=template_path)
    assert "altitude_decay" in str(exc.value)


def test_absent_chart_anchor_raises(template_path, payload, prose, charts) -> None:
    bad = SlotMap(
        text_paths={},
        charts=(ChartSlot("altitude_decay", "존재하지 않는 도표 라벨", "down"),),
    )
    with pytest.raises(FillError) as exc:
        fill_daily_report(payload, prose, charts, template_path=template_path, slotmap=bad)
    assert "altitude_decay" in str(exc.value)


def test_fill_error_lists_offending_slots() -> None:
    err = FillError("text slot(s) failed to fill", slots=["a", "b"])
    assert err.slots == ["a", "b"]
    assert "a" in str(err) and "b" in str(err)


# --------------------------------------------------------------------------- #
# default-asset path (the bundled template currently lacks the labels)
# --------------------------------------------------------------------------- #


def test_default_template_lacks_labels_raises(payload, prose, charts) -> None:
    # Documents the user-facing blocker: the shipped daily_report.hwpx has none of
    # the slotmap's unique anchor labels yet, so the default path must RAISE
    # rather than silently produce an unfilled report.
    with pytest.raises(FillError):
        fill_daily_report(payload, prose, charts)


def test_default_template_loads_via_resources() -> None:
    # The asset is reachable CWD-independently (Celery worker safety).
    data = hwpx_filler._load_default_template()
    assert data.startswith(PK_SIGNATURE)
