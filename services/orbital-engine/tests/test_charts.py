"""Tests for the daily-report chart renderers (T4).

Each of the four chart kinds is checked for: a happy path (valid series → nonempty
PNG bytes), an empty-series path (→ a valid placeholder PNG, no exception), and a
single-point path. We assert the return type is ``bytes`` and that it carries the
PNG signature; we deliberately do not assert on pixel content. We also confirm the
CJK-font helper never raises regardless of what fonts the host has.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orbital_engine.reports import charts
from orbital_engine.reports.schemas import TimeSeriesPoint, TimeSeriesSeries

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 0, 0, tzinfo=UTC)


def _assert_png(data: object) -> None:
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data.startswith(PNG_SIGNATURE)


# --------------------------------------------------------------------------- #
# font helper
# --------------------------------------------------------------------------- #


def test_use_cjk_font_does_not_raise() -> None:
    # Must work whether or not the host has a Hangul font installed.
    result = charts._use_cjk_font()
    assert isinstance(result, bool)


def test_label_helper_returns_str() -> None:
    assert isinstance(charts._label("한국어", "ascii"), str)


# --------------------------------------------------------------------------- #
# altitude_decay (payload-fed)
# --------------------------------------------------------------------------- #


def _altitude_series(points: list[TimeSeriesPoint]) -> list[TimeSeriesSeries]:
    return [TimeSeriesSeries(object_id="A1", object_name="SAT-A", points=points)]


def test_altitude_decay_happy() -> None:
    series = _altitude_series(
        [
            TimeSeriesPoint(epoch=_dt(1), apogee_km=820.0, perigee_km=790.0),
            TimeSeriesPoint(epoch=_dt(2), apogee_km=815.0, perigee_km=785.0),
            TimeSeriesPoint(epoch=_dt(3), apogee_km=808.0, perigee_km=778.0),
        ]
    )
    _assert_png(charts.render_chart("altitude_decay", series))


def test_altitude_decay_empty() -> None:
    _assert_png(charts.render_chart("altitude_decay", []))


def test_altitude_decay_single_point() -> None:
    series = _altitude_series([TimeSeriesPoint(epoch=_dt(1), apogee_km=820.0, perigee_km=790.0)])
    _assert_png(charts.render_chart("altitude_decay", series))


def test_altitude_decay_all_none_points_is_placeholder() -> None:
    # Points exist but every altitude field is None → graceful placeholder.
    series = _altitude_series([TimeSeriesPoint(epoch=_dt(1), apogee_km=None, perigee_km=None)])
    _assert_png(charts.render_chart("altitude_decay", series))


# --------------------------------------------------------------------------- #
# longitude_date (arg-fed)
# --------------------------------------------------------------------------- #


def test_longitude_date_happy() -> None:
    epochs = [_dt(1), _dt(2), _dt(3)]
    lons = [128.1, 128.3, 128.0]
    _assert_png(charts.render_chart("longitude_date", epochs, lons, "SAT-A"))


def test_longitude_date_empty() -> None:
    _assert_png(charts.render_chart("longitude_date", [], []))


def test_longitude_date_single_point() -> None:
    _assert_png(charts.render_chart("longitude_date", [_dt(1)], [128.1]))


# --------------------------------------------------------------------------- #
# relative_position (arg-fed)
# --------------------------------------------------------------------------- #


def test_relative_position_happy() -> None:
    epochs = [_dt(1), _dt(2), _dt(3)]
    rng = [12.5, 9.8, 4.2]
    _assert_png(charts.render_chart("relative_position", epochs, rng, "SAT-A", "SAT-B"))


def test_relative_position_empty() -> None:
    _assert_png(charts.render_chart("relative_position", [], []))


def test_relative_position_single_point() -> None:
    _assert_png(charts.render_chart("relative_position", [_dt(1)], [12.5]))


# --------------------------------------------------------------------------- #
# orbit_3d (arg-fed)
# --------------------------------------------------------------------------- #


def test_orbit_3d_happy() -> None:
    xs = [7000.0, 0.0, -7000.0, 0.0]
    ys = [0.0, 7000.0, 0.0, -7000.0]
    zs = [0.0, 100.0, 0.0, -100.0]
    _assert_png(charts.render_chart("orbit_3d", xs, ys, zs, "SAT-A"))


def test_orbit_3d_empty() -> None:
    _assert_png(charts.render_chart("orbit_3d", [], [], []))


def test_orbit_3d_single_point() -> None:
    _assert_png(charts.render_chart("orbit_3d", [7000.0], [0.0], [0.0]))


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #


def test_render_chart_unknown_kind_raises() -> None:
    with pytest.raises(ValueError):
        charts.render_chart("not_a_chart", [])
