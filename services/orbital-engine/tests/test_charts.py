"""Engine-side §5b chart renderer: render_debris_density → valid PNG bytes.

The renderer is headless (Agg) and single-purpose: it bins debris mean-shell
altitudes and draws the 고도별 잔해 밀도 bars. These tests assert it always returns
a real PNG (\\x89PNG header) for representative inputs — many values, a single
value, and the empty placeholder case — and that it does not leak figures.
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from orbital_engine.reports.charts import render_debris_density, render_fallback_image

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
