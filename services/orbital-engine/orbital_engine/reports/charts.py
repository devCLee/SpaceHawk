"""Chart renderers for the daily report (HWPX) — PNG bytes, deterministic.

T4 turns the deterministic :class:`~orbital_engine.reports.schemas.DailyReportPayload`
time series (and a few caller-supplied series) into the four chart kinds the HWPX
sample uses:

    "altitude_decay"    — apogee/perigee altitude over time per object
                          (고도 변화, fed by ``payload.time_series``)
    "longitude_date"    — longitude vs date (경도-일자)
    "relative_position" — relative position between two objects (상대위치)
    "orbit_3d"          — 3D orbit path (3D궤도)

Only ``altitude_decay`` has data in the payload today (``TimeSeriesSeries`` carries
apogee/perigee per epoch). The payload carries no longitude, relative-position, or
ECI/orbit-path samples, so those three renderers take their series as explicit
function arguments. When called with no data they render a labeled placeholder
PNG rather than inventing payload fields.

Backend
=======
The non-interactive **Agg** backend is forced *before* pyplot is imported, so no
window is ever opened and the module is safe to import in headless test/CI runs.

Korean font
===========
matplotlib's default font cannot render Hangul (it draws tofu boxes and emits
"missing glyph" warnings). :func:`_use_cjk_font` probes the font manager for a
CJK-capable family (e.g. ``Malgun Gothic`` on Windows, ``Noto Sans CJK`` /
``NanumGothic`` elsewhere). If one is found it is set as the active family and the
renderers use the native Korean labels. If none is found the helper returns
``False`` and the renderers fall back to ASCII/romanized labels, so output stays
clean and deterministic on any host. The probe never raises. ``axes.unicode_minus``
is disabled so a CJK font's minus glyph never trips the negative-number renderer.

Every renderer saves to an in-memory buffer and closes its figure, so no global
matplotlib state leaks between calls and figures are not held in memory.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # headless: pick the backend before importing pyplot

import matplotlib.pyplot as plt  # noqa: E402  (must follow matplotlib.use)
from matplotlib import font_manager  # noqa: E402

from orbital_engine.reports.schemas import TimeSeriesSeries  # noqa: E402

# CJK families to try, most-preferred first. The first one the host actually has
# installed wins; if none is present we romanize the labels instead.
_CJK_FONT_CANDIDATES: tuple[str, ...] = (
    "Malgun Gothic",
    "Noto Sans CJK KR",
    "Noto Sans KR",
    "NanumGothic",
    "Nanum Gothic",
    "AppleGothic",
    "Source Han Sans KR",
    "Microsoft YaHei",
)

# Resolved once per process: True once a CJK family is active, False if none found.
# ``None`` means "not yet probed".
_cjk_active: bool | None = None


def _use_cjk_font() -> bool:
    """Activate a CJK-capable font family if the host has one.

    Returns ``True`` when a Hangul-capable family is now the matplotlib default
    (so renderers may use Korean labels), ``False`` when none is installed (so
    renderers must romanize). Memoized; never raises.
    """
    global _cjk_active
    if _cjk_active is not None:
        return _cjk_active

    matplotlib.rcParams["axes.unicode_minus"] = False
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in _CJK_FONT_CANDIDATES:
            if name in available:
                matplotlib.rcParams["font.family"] = name
                _cjk_active = True
                return True
    except Exception:
        # Font-manager hiccups must never break chart rendering.
        pass

    _cjk_active = False
    return False


def _label(korean: str, ascii_fallback: str) -> str:
    """Pick the Korean label when a CJK font is active, else the ASCII fallback."""
    return korean if _use_cjk_font() else ascii_fallback


def _finish(fig: plt.Figure) -> bytes:
    """Render ``fig`` to PNG bytes and close it (no figure leaks)."""
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


def _placeholder(title: str) -> bytes:
    """A valid PNG carrying ``title`` and a 'no data' note (empty-series case)."""
    _use_cjk_font()
    fig, ax = plt.subplots(figsize=(6.0, 3.5))
    ax.set_title(title)
    ax.text(
        0.5,
        0.5,
        _label("데이터 없음", "no data"),
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=14,
        color="0.4",
    )
    ax.set_xticks([])
    ax.set_yticks([])
    return _finish(fig)


def render_altitude_decay(series: Sequence[TimeSeriesSeries]) -> bytes:
    """고도 변화: apogee & perigee altitude over time, one pair of lines per object.

    Data source: ``payload.time_series`` (:class:`TimeSeriesSeries`). Each point's
    ``apogee_km`` / ``perigee_km`` may be ``None`` and is skipped; an object with
    no usable points contributes nothing. Empty input → placeholder PNG.
    """
    title = _label("고도 변화 (원지점/근지점)", "Altitude decay (apogee/perigee)")
    if not series:
        return _placeholder(title)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    plotted = False
    for obj in series:
        apo_x: list[datetime] = []
        apo_y: list[float] = []
        per_x: list[datetime] = []
        per_y: list[float] = []
        for pt in obj.points:
            if pt.apogee_km is not None:
                apo_x.append(pt.epoch)
                apo_y.append(pt.apogee_km)
            if pt.perigee_km is not None:
                per_x.append(pt.epoch)
                per_y.append(pt.perigee_km)
        if apo_y:
            ax.plot(apo_x, apo_y, marker="o", label=f"{obj.object_name} apogee")
            plotted = True
        if per_y:
            ax.plot(per_x, per_y, marker="o", linestyle="--", label=f"{obj.object_name} perigee")
            plotted = True

    if not plotted:
        plt.close(fig)
        return _placeholder(title)

    ax.set_title(title)
    ax.set_xlabel(_label("일자", "date"))
    ax.set_ylabel(_label("고도 (km)", "altitude (km)"))
    ax.grid(True, linewidth=0.3, alpha=0.6)
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    return _finish(fig)


def render_longitude_date(
    epochs: Sequence[datetime],
    longitudes_deg: Sequence[float],
    object_name: str | None = None,
) -> bytes:
    """경도-일자: longitude (deg) vs date for one object.

    The payload carries no longitude series, so the data is taken as explicit
    arguments. ``epochs`` and ``longitudes_deg`` are paired element-wise; the
    shorter length wins. Empty (or length-zero) input → placeholder PNG.
    """
    name = object_name or _label("객체", "object")
    title = _label(f"경도-일자 ({name})", f"Longitude vs date ({name})")
    n = min(len(epochs), len(longitudes_deg))
    if n == 0:
        return _placeholder(title)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.plot(list(epochs[:n]), list(longitudes_deg[:n]), marker="o", color="#1f77b4")
    ax.set_title(title)
    ax.set_xlabel(_label("일자", "date"))
    ax.set_ylabel(_label("경도 (도)", "longitude (deg)"))
    ax.grid(True, linewidth=0.3, alpha=0.6)
    fig.autofmt_xdate()
    return _finish(fig)


def render_relative_position(
    epochs: Sequence[datetime],
    range_km: Sequence[float],
    primary_name: str | None = None,
    secondary_name: str | None = None,
) -> bytes:
    """상대위치: relative range (km) between two objects over time.

    The payload carries no relative-position series, so the data is taken as
    explicit arguments. ``epochs`` and ``range_km`` are paired element-wise.
    Empty input → placeholder PNG.
    """
    pair = f"{primary_name or 'A'} / {secondary_name or 'B'}"
    title = _label(f"상대위치 거리 ({pair})", f"Relative position range ({pair})")
    n = min(len(epochs), len(range_km))
    if n == 0:
        return _placeholder(title)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.plot(list(epochs[:n]), list(range_km[:n]), marker="o", color="#d62728")
    ax.set_title(title)
    ax.set_xlabel(_label("일자", "date"))
    ax.set_ylabel(_label("상대거리 (km)", "relative range (km)"))
    ax.grid(True, linewidth=0.3, alpha=0.6)
    fig.autofmt_xdate()
    return _finish(fig)


def render_orbit_3d(
    xs_km: Sequence[float],
    ys_km: Sequence[float],
    zs_km: Sequence[float],
    object_name: str | None = None,
) -> bytes:
    """3D궤도: a 3D orbit path from ECI position samples (km).

    The payload carries no orbit-path samples, so x/y/z are taken as explicit
    arguments. The three sequences are paired element-wise; the shortest wins.
    Empty input → placeholder PNG. A single point still renders (drawn as a dot).
    """
    name = object_name or _label("객체", "object")
    title = _label(f"3D 궤도 ({name})", f"3D orbit ({name})")
    n = min(len(xs_km), len(ys_km), len(zs_km))
    if n == 0:
        return _placeholder(title)

    fig = plt.figure(figsize=(6.0, 5.0))
    ax = fig.add_subplot(111, projection="3d")
    x, y, z = list(xs_km[:n]), list(ys_km[:n]), list(zs_km[:n])
    if n == 1:
        ax.scatter(x, y, z, color="#2ca02c")
    else:
        ax.plot(x, y, z, color="#2ca02c")
    ax.set_title(title)
    ax.set_xlabel("X (km)")
    ax.set_ylabel("Y (km)")
    ax.set_zlabel("Z (km)")
    return _finish(fig)


_RENDERERS = {
    "altitude_decay": render_altitude_decay,
    "longitude_date": render_longitude_date,
    "relative_position": render_relative_position,
    "orbit_3d": render_orbit_3d,
}


def render_chart(kind: str, *args: object, **kwargs: object) -> bytes:
    """Dispatch to the renderer for ``kind`` and return its PNG bytes.

    ``kind`` is one of ``"altitude_decay"``, ``"longitude_date"``,
    ``"relative_position"``, ``"orbit_3d"``. Positional/keyword arguments are
    forwarded verbatim to the matching renderer. Unknown ``kind`` raises
    ``ValueError``.
    """
    try:
        renderer = _RENDERERS[kind]
    except KeyError:
        raise ValueError(
            f"unknown chart kind {kind!r}; expected one of {sorted(_RENDERERS)}"
        ) from None
    return renderer(*args, **kwargs)  # type: ignore[arg-type]
