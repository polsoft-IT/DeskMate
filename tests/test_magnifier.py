"""Tests for magnifier.py zoom clamping and crop-bounds maths.

These exercise only the pure helpers so they run without a display or the
Windows low-level mouse hook.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import magnifier as m  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_module_state(monkeypatch):
    """Keep zoom isolated and stop apply_zoom touching the real Tk widget."""
    original = m.zoom
    monkeypatch.setattr(m, "_set_hud", lambda: None)
    yield
    m.zoom = original


# --------------------------------------------------------------------------
# apply_zoom clamping
# --------------------------------------------------------------------------

def test_apply_zoom_increases_on_positive_step():
    m.zoom = 3.0
    m.apply_zoom(1)
    assert m.zoom == pytest.approx(3.0 * m.ZOOM_STEP)


def test_apply_zoom_decreases_on_negative_step():
    m.zoom = 3.0
    m.apply_zoom(-1)
    assert m.zoom == pytest.approx(3.0 / m.ZOOM_STEP)


def test_apply_zoom_clamped_at_max():
    m.zoom = m.ZOOM_MAX
    m.apply_zoom(1)
    assert m.zoom == m.ZOOM_MAX


def test_apply_zoom_clamped_at_min():
    m.zoom = m.ZOOM_MIN
    m.apply_zoom(-1)
    assert m.zoom == m.ZOOM_MIN


def test_apply_zoom_stays_within_bounds_over_many_steps():
    m.zoom = 3.0
    for _ in range(50):
        m.apply_zoom(1)
    assert m.ZOOM_MIN <= m.zoom <= m.ZOOM_MAX
    for _ in range(100):
        m.apply_zoom(-1)
    assert m.ZOOM_MIN <= m.zoom <= m.ZOOM_MAX


# --------------------------------------------------------------------------
# crop-bounds maths
# --------------------------------------------------------------------------

def _crop_bounds(zoom, src_w, src_h):
    """Mirror the crop computation from update_lens().

    src_w/src_h are already the *effective* grab size, i.e. what the screen
    grab produced, so the crop rectangle must never exceed them.
    """
    lens_w = m.LENS_W / zoom
    lens_h = m.LENS_H / zoom
    x1 = max(0, (m.LENS_W - lens_w) / 2)
    y1 = max(0, (m.LENS_H - lens_h) / 2)
    x2 = min(src_w, x1 + lens_w)
    y2 = min(src_h, y1 + lens_h)
    return x1, y1, x2, y2


def test_crop_bounds_valid_at_high_zoom():
    x1, y1, x2, y2 = _crop_bounds(m.ZOOM_MAX, m.VS_W, m.VS_H)
    assert 0 <= x1 < x2 <= m.VS_W
    assert 0 <= y1 < y2 <= m.VS_H


def test_crop_bounds_valid_at_min_zoom():
    # At the lowest zoom the lens asks for more pixels than a small grab has.
    x1, y1, x2, y2 = _crop_bounds(m.ZOOM_MIN, m.VS_W, m.VS_H)
    assert x2 <= m.VS_W
    assert y2 <= m.VS_H
    assert x2 > x1
    assert y2 > y1


def test_crop_bounds_clamped_when_source_smaller_than_lens():
    # Simulate a tiny grab (e.g. a just-connected small monitor).
    src_w, src_h = 100, 80
    x1, y1, x2, y2 = _crop_bounds(1.0, src_w, src_h)
    assert x2 <= src_w
    assert y2 <= src_h
    assert x1 >= 0
    assert y1 >= 0


def test_crop_bounds_odd_zoom_values():
    for zoom in (1.1, 2.5, 7.3):
        x1, y1, x2, y2 = _crop_bounds(zoom, m.VS_W, m.VS_H)
        assert 0 <= x1 < x2 <= m.VS_W
        assert 0 <= y1 < y2 <= m.VS_H
