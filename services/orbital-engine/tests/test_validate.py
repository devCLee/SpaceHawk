"""HWPX safety-gate tests (discussion #184): validate-or-discard.

A valid, freshly built document must pass :func:`validate_hwpx`; a corrupted
package (truncated zip, garbled ``section0.xml``), as well as non-zip / empty
bytes, must raise :class:`ReportValidationError` rather than slip through or
blow up with an unhandled exception. The round-trip case proves the open ->
save -> open stability the #184 gate requires.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from hwpx import HwpxDocument

from orbital_engine.reports.validate import ReportValidationError, validate_hwpx


def _valid_hwpx_bytes() -> bytes:
    """A minimal but well-formed HWPX produced via the library itself."""
    document = HwpxDocument.new()
    document.add_paragraph("SpaceHawk daily report — validation fixture")
    return document.to_bytes()


def _garble_part(data: bytes, suffix: str, replacement: bytes) -> bytes:
    """Return a copy of the HWPX zip with the part ending in *suffix* garbled."""
    source = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename.endswith(suffix):
                content = replacement
            zout.writestr(item, content)
    return out.getvalue()


def test_valid_document_passes() -> None:
    # A freshly built, well-formed document passes the gate (returns None).
    assert validate_hwpx(_valid_hwpx_bytes()) is None


def test_round_trip_stable() -> None:
    # The same bytes survive open -> save -> open inside the gate (#184 criterion).
    data = _valid_hwpx_bytes()
    # Sanity: an independent open->save->open also yields a valid package.
    reopened = HwpxDocument.open(HwpxDocument.open(data).to_bytes()).to_bytes()
    assert validate_hwpx(reopened) is None


def test_truncated_zip_raises() -> None:
    data = _valid_hwpx_bytes()
    with pytest.raises(ReportValidationError):
        validate_hwpx(data[: len(data) // 2])


def test_garbled_section_raises() -> None:
    corrupt = _garble_part(_valid_hwpx_bytes(), "section0.xml", b"<broken><<<not valid xml")
    with pytest.raises(ReportValidationError):
        validate_hwpx(corrupt)


def test_empty_bytes_raises() -> None:
    with pytest.raises(ReportValidationError):
        validate_hwpx(b"")


def test_non_zip_bytes_raises() -> None:
    with pytest.raises(ReportValidationError):
        validate_hwpx(b"this is plainly not an HWPX archive")
