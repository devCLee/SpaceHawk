"""Engine-side chart rendering for the daily HWPX report (§5b).

Two §5b renderers, both engine-side so the charts always appear regardless of the
web UI: :func:`render_debris_density` turns the §5 scored debris set's mean shell
altitudes into the **고도별 잔해 밀도** bar chart, and :func:`render_debris_heatmap`
turns the assembler's risk-weighted lon×lat grid into the **2D 잔해 밀도 히트맵**.
Both bin the SAME scored debris set the assembler counts in ``debris_risk_counts``,
so the engine output stays internally consistent.

Headless by construction: the Agg backend is selected *before* pyplot is
imported, so this works on a worker with no display. Korean labels render with an
autodetected CJK font (Malgun Gothic on this host) and fall back to the default
sans (ASCII labels) when no CJK face is installed, so the render never crashes on
a barebones box. Every figure is closed after rendering — no figure-leak.
"""

from __future__ import annotations

from collections.abc import Sequence

import matplotlib

matplotlib.use("Agg")  # headless: must precede pyplot import

import io  # noqa: E402 - after the backend is fixed
import math  # noqa: E402 - after the backend is fixed

import matplotlib.pyplot as plt  # noqa: E402 - after the backend is fixed
from matplotlib import font_manager  # noqa: E402 - after the backend is fixed
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402 - after the backend is fixed

# --- Altitude binning ---------------------------------------------------------
# LEO (0–2000 km) is the debris-dense regime, so it gets fine 200 km bins; the
# sparse MEO/GEO tail is folded into two wide catch-all bins. Each bin is a
# half-open band [lo, hi) except the last (GEO+) which is open-ended. Edits here
# must keep the labels in lock-step with the edges.
_LEO_TOP_KM = 2000.0
_LEO_BIN_WIDTH_KM = 200.0
_MEO_TOP_KM = 35000.0  # below this (and >= LEO top) = MEO; at/above = GEO+

#: Bar labels, low→high. The LEO bands are generated; MEO/GEO are appended.
_BIN_LABELS: list[str] = [
    f"{int(lo)}–{int(lo + _LEO_BIN_WIDTH_KM)}"
    for lo in range(0, int(_LEO_TOP_KM), int(_LEO_BIN_WIDTH_KM))
] + ["MEO\n(2k–35k)", "GEO+\n(≥35k)"]

# --- Korean text --------------------------------------------------------------
_CJK_FONT_CANDIDATES = ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Gulim", "Batang")
_TITLE_KO = "고도별 잔해 밀도"
_X_LABEL_KO = "고도 (km)"
_Y_LABEL_KO = "잔해 수"
_EMPTY_KO = "잔해 데이터 없음"
# ASCII fallbacks when no CJK face is available (keeps the PNG legible anywhere).
_TITLE_EN = "Debris density by altitude"
_X_LABEL_EN = "Altitude (km)"
_Y_LABEL_EN = "Debris count"
_EMPTY_EN = "No debris data"

# Default label for the missing-image fallback graphic (이미지 없음 = "no image").
_FALLBACK_LABEL_KO = "이미지 없음"
_FALLBACK_LABEL_EN = "No image"

# --- §5b 2D 잔해 밀도 히트맵 --------------------------------------------------
# Heat ramp stops, blue→cyan→green→yellow→orange→red, mirroring the web's
# HEAT_STOPS in DebrisHeatmap2D.tsx (positions + RGB). A LinearSegmentedColormap
# built from these gives the same visual ramp under matplotlib's imshow.
_HEAT_STOPS: tuple[tuple[float, tuple[float, float, float]], ...] = (
    (0.0, (30 / 255, 60 / 255, 160 / 255)),
    (0.25, (0 / 255, 200 / 255, 220 / 255)),
    (0.5, (40 / 255, 210 / 255, 90 / 255)),
    (0.7, (240 / 255, 220 / 255, 60 / 255)),
    (0.85, (245 / 255, 150 / 255, 40 / 255)),
    (1.0, (239 / 255, 68 / 255, 68 / 255)),
)
_HEAT_CMAP = LinearSegmentedColormap.from_list("debris_heat", _HEAT_STOPS)

# Lon×lat grid shape (must match the assembler's _bin_heatmap: [GRID_H][GRID_W]).
_HEATMAP_GRID_W = 144
_HEATMAP_GRID_H = 72
_HEATMAP_LON_TICKS = (-180, -90, 0, 90, 180)
_HEATMAP_LAT_TICKS = (90, 45, 0, -45, -90)

_HEATMAP_TITLE_KO = "2D 잔해 밀도 히트맵"
_HEATMAP_X_LABEL_KO = "경도 (°)"
_HEATMAP_Y_LABEL_KO = "위도 (°)"
_HEATMAP_EMPTY_KO = "잔해 위치 데이터 없음"
_HEATMAP_TITLE_EN = "2D debris density heatmap"
_HEATMAP_X_LABEL_EN = "Longitude (°)"
_HEATMAP_Y_LABEL_EN = "Latitude (°)"
_HEATMAP_EMPTY_EN = "No debris position data"


def _cjk_font() -> str | None:
    """First installed CJK font family from the candidate list, or None."""
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_FONT_CANDIDATES:
        if name in available:
            return name
    return None


def _bin_counts(altitudes_km: Sequence[float]) -> list[int]:
    """Tally altitudes into the LEO 200 km bands + MEO + GEO catch-alls."""
    n_leo = int(_LEO_TOP_KM // _LEO_BIN_WIDTH_KM)
    counts = [0] * (n_leo + 2)  # LEO bands + MEO + GEO
    for h in altitudes_km:
        if h < _LEO_TOP_KM:
            idx = max(0, int(h // _LEO_BIN_WIDTH_KM))
            counts[min(idx, n_leo - 1)] += 1
        elif h < _MEO_TOP_KM:
            counts[n_leo] += 1  # MEO
        else:
            counts[n_leo + 1] += 1  # GEO+
    return counts


def _figure_to_png(fig: plt.Figure) -> bytes:
    """Serialize a figure to PNG bytes and close it (no figure-leak)."""
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        return buf.getvalue()
    finally:
        plt.close(fig)


def render_debris_density(altitudes_km: Sequence[float]) -> bytes:
    """Render the §5b 고도별 잔해 밀도 bar chart as PNG bytes.

    Bins ``altitudes_km`` (mean shell altitudes of the scored debris set) into
    LEO 200 km bands plus MEO / GEO+ catch-alls and draws the per-band counts.
    Empty input yields a labeled placeholder PNG rather than crashing. The label
    language follows font availability: Korean when a CJK face is installed
    (Malgun Gothic on this host), ASCII otherwise.
    """
    font = _cjk_font()
    ko = font is not None
    title = _TITLE_KO if ko else _TITLE_EN
    x_label = _X_LABEL_KO if ko else _X_LABEL_EN
    y_label = _Y_LABEL_KO if ko else _Y_LABEL_EN
    empty_label = _EMPTY_KO if ko else _EMPTY_EN

    rc: dict[str, object] = {"axes.unicode_minus": False}
    if font is not None:
        rc["font.family"] = font

    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(8.0, 4.0))

        if not altitudes_km:
            ax.text(0.5, 0.5, empty_label, ha="center", va="center", fontsize=14, transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(title)
            return _figure_to_png(fig)

        counts = _bin_counts(altitudes_km)
        positions = range(len(counts))
        ax.bar(positions, counts, color="#c0392b", edgecolor="#7b241c", width=0.85)
        ax.set_xticks(list(positions))
        ax.set_xticklabels(_BIN_LABELS, rotation=60, ha="right", fontsize=7)
        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.margins(x=0.01)
        return _figure_to_png(fig)


def _heatmap_is_empty(grid: Sequence[Sequence[float]]) -> bool:
    """True when ``grid`` is missing, mis-shaped, or all non-positive (placeholder)."""
    if not grid:
        return True
    return all(v <= 0.0 for row in grid for v in row)


def render_debris_heatmap(grid: Sequence[Sequence[float]]) -> bytes:
    """Render the §5b 2D 잔해 밀도 히트맵 as PNG bytes.

    ``grid`` is the risk-weighted lon×lat density grid from the assembler
    (``[GRID_H][GRID_W]`` = 72×144, lat 90→-90 top→bottom, lon -180→180), mirroring
    ``DebrisHeatmap2D.tsx``. Drawn equirectangular via ``imshow`` with the blue→red
    heat ramp colormap and sqrt-scaled intensity (``t = sqrt(value / max)``) so low
    densities lift, exactly like the web. Lon/lat axis ticks + Korean titles (CJK
    font autodetect, ASCII fallback). An empty / all-zero / mis-shaped grid yields a
    labeled placeholder PNG. The figure is always closed (no figure-leak).
    """
    font = _cjk_font()
    ko = font is not None
    title = _HEATMAP_TITLE_KO if ko else _HEATMAP_TITLE_EN
    x_label = _HEATMAP_X_LABEL_KO if ko else _HEATMAP_X_LABEL_EN
    y_label = _HEATMAP_Y_LABEL_KO if ko else _HEATMAP_Y_LABEL_EN
    empty_label = _HEATMAP_EMPTY_KO if ko else _HEATMAP_EMPTY_EN

    rc: dict[str, object] = {"axes.unicode_minus": False}
    if font is not None:
        rc["font.family"] = font

    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(8.0, 4.0))

        if _heatmap_is_empty(grid):
            ax.text(0.5, 0.5, empty_label, ha="center", va="center", fontsize=14, transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(title)
            return _figure_to_png(fig)

        peak = max(v for row in grid for v in row)
        # sqrt intensity (t = sqrt(value / max)), matching the web's lift of low density.
        scaled = [[math.sqrt(v / peak) if v > 0.0 else 0.0 for v in row] for row in grid]

        ax.set_facecolor("#0a0f1a")
        ax.imshow(
            scaled,
            cmap=_HEAT_CMAP,
            origin="upper",  # row 0 = lat +90 (top), matching the grid orientation
            extent=(-180.0, 180.0, -90.0, 90.0),
            aspect="auto",
            vmin=0.0,
            vmax=1.0,
            interpolation="bilinear",
        )
        ax.set_xticks(list(_HEATMAP_LON_TICKS))
        ax.set_yticks(list(_HEATMAP_LAT_TICKS))
        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        return _figure_to_png(fig)


def render_fallback_image(label: str = _FALLBACK_LABEL_KO) -> bytes:
    """Render a small placeholder PNG with ``label`` centered on a neutral panel.

    Used by the HWPX filler to fill any image anchor whose real image is absent
    (a country globe the web did not supply, the heatmap, a failed embed) so the
    cell shows a clean graphic instead of the template's placeholder text. The
    label follows font availability like :func:`render_debris_density`: the Korean
    default renders when a CJK face is installed, otherwise an ASCII fallback is
    substituted for the Korean default so the PNG stays legible anywhere.
    """
    font = _cjk_font()
    if font is None and label == _FALLBACK_LABEL_KO:
        label = _FALLBACK_LABEL_EN

    rc: dict[str, object] = {"axes.unicode_minus": False}
    if font is not None:
        rc["font.family"] = font

    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(3.0, 2.0))
        fig.patch.set_facecolor("#ecf0f1")
        ax.set_facecolor("#ecf0f1")
        ax.text(0.5, 0.5, label, ha="center", va="center", fontsize=16, color="#7f8c8d")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        return _figure_to_png(fig)
