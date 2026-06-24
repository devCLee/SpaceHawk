"""Engine-side §5b chart renderers: density bars + 2D heatmap → valid PNG bytes.

The renderers are headless (Agg). ``render_debris_density`` bins debris mean-shell
altitudes into the 고도별 잔해 밀도 bars; ``render_debris_heatmap`` draws the
risk-weighted lon×lat grid as the 2D 잔해 밀도 히트맵. These tests assert both always
return a real PNG (\\x89PNG header) for representative inputs — many values, a single
value, the empty placeholder case, and (for the heatmap) a non-empty grid + an
all-zero grid — and that neither leaks figures.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from orbital_engine.reports.charts import (
    render_debris_density,
    render_debris_heatmap,
    render_fallback_image,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

GRID_W = 144
GRID_H = 72


def _zero_grid() -> list[list[float]]:
    return [[0.0] * GRID_W for _ in range(GRID_H)]


def _sample_grid() -> list[list[float]]:
    """A non-empty 72×144 grid with a few risk-weighted hot cells."""
    grid = _zero_grid()
    grid[10][20] = 1.0  # a Critical cell
    grid[10][21] = 0.7  # an adjacent High cell
    grid[35][72] = 0.4  # equator-ish Medium cell
    grid[60][130] = 0.2  # a far Low cell
    return grid


def test_render_many_altitudes_is_valid_png() -> None:
    # Spread across LEO bands + MEO + GEO so multiple bins are populated.
    altitudes = [350.0, 420.0, 550.0, 780.0, 820.0, 850.0, 1400.0, 1900.0, 20200.0, 35786.0]
    png = render_debris_density(altitudes)
    assert isinstance(png, bytes)
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 1000  # a real rendered chart, not a stub


def test_render_single_value_is_valid_png() -> None:
    png = render_debris_density([800.0])
    assert png.startswith(PNG_SIGNATURE)


def test_render_empty_yields_placeholder_png() -> None:
    png = render_debris_density([])
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 0


def test_render_does_not_leak_figures() -> None:
    plt.close("all")
    before = len(plt.get_fignums())
    render_debris_density([400.0, 800.0, 1500.0])
    render_debris_density([])
    after = len(plt.get_fignums())
    assert after == before  # every figure closed


def test_render_heatmap_non_empty_grid_is_valid_png() -> None:
    png = render_debris_heatmap(_sample_grid())
    assert isinstance(png, bytes)
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 1000  # a real rendered heatmap, not a stub


def test_render_heatmap_empty_grid_yields_placeholder_png() -> None:
    png = render_debris_heatmap([])
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 0


def test_render_heatmap_all_zero_grid_yields_placeholder_png() -> None:
    # An all-zero grid (debris exist but bin to nothing positive) is treated as empty.
    png = render_debris_heatmap(_zero_grid())
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 0


def test_render_heatmap_does_not_leak_figures() -> None:
    plt.close("all")
    before = len(plt.get_fignums())
    render_debris_heatmap(_sample_grid())
    render_debris_heatmap([])
    render_debris_heatmap(_zero_grid())
    after = len(plt.get_fignums())
    assert after == before  # every figure closed


def test_render_fallback_image_is_valid_png() -> None:
    png = render_fallback_image()
    assert isinstance(png, bytes)
    assert png.startswith(PNG_SIGNATURE)
    assert len(png) > 0


def test_render_fallback_image_custom_label_is_valid_png() -> None:
    png = render_fallback_image("히트맵 없음")
    assert png.startswith(PNG_SIGNATURE)


def test_render_fallback_does_not_leak_figures() -> None:
    plt.close("all")
    before = len(plt.get_fignums())
    render_fallback_image()
    after = len(plt.get_fignums())
    assert after == before  # figure closed
