"""Engine-side chart rendering for the daily HWPX report (§5b).

A single, focused renderer: :func:`render_debris_density` turns the §5 scored
debris set's mean shell altitudes into the **고도별 잔해 밀도** bar chart embedded
at the §5b left anchor. The companion 2D 잔해 밀도 히트맵 stays web-supplied; this
module renders only the by-altitude density bars so the engine output stays
consistent with ``debris_risk_counts`` (it bins the SAME altitude set the
assembler scored).

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

import matplotlib.pyplot as plt  # noqa: E402 - after the backend is fixed
from matplotlib import font_manager  # noqa: E402 - after the backend is fixed

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
