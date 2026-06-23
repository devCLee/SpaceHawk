"""Safety gate: an HWPX must PASS validation + round-trip before it ships.

DISCUSSION #184 — VALIDATE-OR-DISCARD
=====================================

``python-hwpx`` is a young library. A file it produces may open fine in a
lenient editor (Hancom Office) yet be subtly malformed in a way that breaks on
a later edit/resave, or in a stricter consumer. "It opens" is therefore *not*
sufficient evidence that the artifact is safe to ship.

This module is the gate agreed in discussion #184: every generated HWPX must
pass schema/structure validation **and** survive an open -> save -> open
round-trip before it is ever handed off. On any failure the caller MUST discard
the file rather than ship it.

What the gate checks (in order, fail-fast)
------------------------------------------

1. PACKAGE VALIDATION — :func:`hwpx.validate_package` inspects the OPC archive
   and its parts. It never raises; it returns a report whose ``ok`` is ``False``
   (with error-level issues) for a non-ZIP, empty, truncated, or structurally
   broken package. We raise on any error-level issue.

2. STRUCTURED OPEN — :meth:`hwpx.HwpxDocument.open` parses the document model.
   It raises (``HwpxStructureError``/``HwpxPackageError`` for bad structure,
   ``BadZipFile``/``XMLSyntaxError`` for lower-level corruption) on a file that
   ``validate_package`` may have passed but the model layer rejects. We also run
   :meth:`HwpxDocument.validate` (XML-schema validation of the live document
   state) and raise on error-level issues.

3. ROUND-TRIP — the #184 criterion. We re-serialize the opened document
   (:meth:`HwpxDocument.to_bytes`) and validate + open the *resulting* bytes.
   This proves the file is edit/resave-stable, not merely openable once. If the
   round-trip bytes fail package validation or fail to open, we raise.

Dependency-light by design: only ``python-hwpx`` + stdlib.
"""

from __future__ import annotations

from hwpx import HwpxDocument, validate_package


class ReportValidationError(Exception):
    """An HWPX failed the #184 safety gate and must be discarded.

    ``reason`` is a short stage label; ``issues`` carries any underlying
    detail (validation issue objects or an exception) for diagnostics.
    """

    def __init__(self, reason: str, issues: object = None) -> None:
        self.reason = reason
        self.issues = issues
        detail = f": {issues}" if issues else ""
        super().__init__(f"{reason}{detail}")


def _check_package(data: bytes, stage: str) -> None:
    """Raise if ``data`` is not a structurally valid HWPX package."""
    report = validate_package(data)
    if not report.ok:
        errors = [
            f"{getattr(i, 'part_name', '?')}: {getattr(i, 'message', i)}"
            for i in report.errors
        ]
        raise ReportValidationError(f"{stage}: package validation failed", errors)


def _open(data: bytes, stage: str) -> HwpxDocument:
    """Open ``data`` as a document, translating library errors into the gate error."""
    # Broad catch is intentional: open() surfaces a range of failure types
    # (HwpxStructureError/HwpxPackageError, BadZipFile, XMLSyntaxError, ...);
    # any of them means "not shippable", so all map to the gate error.
    try:
        return HwpxDocument.open(data)
    except Exception as exc:
        raise ReportValidationError(f"{stage}: failed to open document", repr(exc)) from exc


def validate_hwpx(data: bytes) -> None:
    """Validate ``data`` as a shippable HWPX, or raise :class:`ReportValidationError`.

    Returns ``None`` when the bytes pass the full #184 gate (package validation,
    structured open + schema validation, and an open -> save -> open round-trip).
    Raises :class:`ReportValidationError` otherwise. Callers must discard the
    file on raise.
    """
    # 1. Package-level structure (catches non-zip / empty / truncated / garbled).
    _check_package(data, "input")

    # 2. Structured open + XML-schema validation of the live document.
    document = _open(data, "input")
    report = document.validate()
    if not report.ok:
        errors = [str(i) for i in report.errors]
        raise ReportValidationError("input: document schema validation failed", errors)

    # 3. Round-trip: re-serialize, then validate + open the resulting bytes.
    try:
        roundtrip = document.to_bytes()
    except Exception as exc:
        raise ReportValidationError("round-trip: re-serialization failed", repr(exc)) from exc

    _check_package(roundtrip, "round-trip")
    reopened = _open(roundtrip, "round-trip")
    reopened_report = reopened.validate()
    if not reopened_report.ok:
        errors = [str(i) for i in reopened_report.errors]
        raise ReportValidationError("round-trip: document schema validation failed", errors)
