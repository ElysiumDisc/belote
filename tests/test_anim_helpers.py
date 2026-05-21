"""Tests for the 4.8.0 animation toolkit (`belote.ui.anim`).

Covers:
  - Easing math (boundary values)
  - BELOTE_NO_ANIM short-circuits each painted helper
  - Painted helpers always invalidate the render-diff baseline
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

import pytest

from belote.ui import anim

# `belote.ui.render` is shadowed by the re-exported `render()` function — pull
# the actual module from sys.modules.
render = sys.modules["belote.ui.render"]


# ── easing math ────────────────────────────────────────────────────────────


def test_ease_out_quad_endpoints():
    assert anim.ease_out_quad(0.0) == 0.0
    assert anim.ease_out_quad(1.0) == 1.0
    # Decelerating: at t=0.5, output is past 0.5.
    assert anim.ease_out_quad(0.5) == 0.75


def test_ease_in_out_quad_endpoints_and_midpoint():
    assert anim.ease_in_out_quad(0.0) == 0.0
    assert anim.ease_in_out_quad(1.0) == 1.0
    # Symmetric: midpoint is exactly 0.5.
    assert anim.ease_in_out_quad(0.5) == 0.5


def test_ease_out_cubic_endpoints():
    assert anim.ease_out_cubic(0.0) == 0.0
    assert anim.ease_out_cubic(1.0) == 1.0
    # Cubic decel: past quad at midpoint.
    assert anim.ease_out_cubic(0.5) > anim.ease_out_quad(0.5)


# ── BELOTE_NO_ANIM short-circuits ─────────────────────────────────────────


@pytest.fixture
def no_anim(monkeypatch):
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    anim._refresh_animations_enabled_from_env()
    yield
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    anim._refresh_animations_enabled_from_env()


def test_pulse_text_invalidates_diff_under_no_anim(no_anim):
    # Seed a non-None diff baseline, then confirm the helper resets it.
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        anim.pulse_text(5, 5, "hi", frames=8)
    assert render._last_emitted_lines is None
    # The end-state text was painted at the target position.
    assert "hi" in buf.getvalue()


def test_float_text_invalidates_diff_under_no_anim(no_anim):
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        anim.float_text("x", start_row=10, end_row=5, col=1)
    assert render._last_emitted_lines is None


def test_tick_bar_invalidates_diff_under_no_anim(no_anim):
    render._last_emitted_lines = ("dummy",)
    seen: list[int] = []
    anim.tick_bar(0, 5, render_fn=seen.append)
    # No animation frames; just the end-state.
    assert seen == [5]
    assert render._last_emitted_lines is None


# ── Painted helpers always invalidate the diff (with anim enabled) ────────


def test_pulse_text_invalidates_diff_when_enabled(monkeypatch):
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    anim._refresh_animations_enabled_from_env()
    assert anim.animations_enabled() is True
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        # tiny frame_delay so the test runs instantly
        anim.pulse_text(1, 1, "x", frames=1, frame_delay=0.0)
    assert render._last_emitted_lines is None
