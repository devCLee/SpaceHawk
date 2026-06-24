"""Deterministic value formatters shared by the report renderers.

Pure functions that turn typed payload values into the exact display strings the
report shows (km distances, probabilities, UTC stamps, Korean cover date). Kept
in one place so the PDF renderer and any other consumer format numbers
identically — the report's figures must read the same regardless of output
format. None-safe throughout: a missing value renders as an empty string, never
a literal ``None``.
"""

from __future__ import annotations

from datetime import date, datetime

# Korean weekday indexed by date.weekday() (Mon=0 .. Sun=6).
WEEKDAYS_KR = ("월", "화", "수", "목", "금", "토", "일")


def fmt_dt(value: datetime | None) -> str:
    """Render a UTC datetime as ``YYYY-MM-DD HH:MMZ`` (empty for None)."""
    if value is None:
        return ""
    return f"{value:%Y-%m-%d %H:%M}Z"


def fmt_num(value: float | None, digits: int = 2) -> str:
    """Render a float with ``digits`` decimals (empty for None)."""
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def fmt_prob(value: float | None) -> str:
    """Render a collision probability in scientific notation (empty for None)."""
    if value is None:
        return ""
    return f"{value:.2e}"


def fmt_rcs(value: str | float | None) -> str:
    """Render an RCS size (class string or numeric area) (empty for None)."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)


def fmt_apsides(perigee: float | None, apogee: float | None) -> str:
    """Render ``perigee/apogee`` km, omitting absent sides (empty if both None)."""
    if perigee is None and apogee is None:
        return ""
    return f"{fmt_num(perigee)}/{fmt_num(apogee)}"


def country_label(code: str, name: str | None) -> str:
    """Render a country cell as the resolved name, falling back to the code."""
    return name or code


def fmt_cover_date(value: date) -> str:
    """Render a date Korean-style as ``YYYY. MM. DD. (요일)`` (no brackets)."""
    return f"{value.year:04d}. {value.month:02d}. {value.day:02d}. ({WEEKDAYS_KR[value.weekday()]})"
