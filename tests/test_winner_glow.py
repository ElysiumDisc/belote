"""Tests for the 4.8.0 `pulse_winner_glow` trick-end animation."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

import pytest

from belote.game import Seat
from belote.ui.anim import _refresh_animations_enabled_from_env

render = sys.modules["belote.ui.render"]


@pytest.mark.parametrize(
    "seat,label",
    [
        (Seat.NORTH, "North"),
        (Seat.SOUTH, "South"),
        (Seat.EAST, "East"),
        (Seat.WEST, "West"),
    ],
)
def test_pulse_winner_glow_renders_direction_label(monkeypatch, seat, label):
    monkeypatch.setenv("BELOTE_NO_ANIM", "0")
    _refresh_animations_enabled_from_env()
    monkeypatch.setattr(render, "get_term_size", lambda: (80, 24))
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        # Pass reader=None so we hit the time.sleep branch — we override
        # time.sleep to instant via the test scope.
        import time
        monkeypatch.setattr(time, "sleep", lambda _x: None)
        render.pulse_winner_glow(seat, reader=None)
    assert f"{label} wins" in buf.getvalue()
    assert render._last_emitted_lines is None


def test_pulse_winner_glow_short_circuits_under_no_anim(monkeypatch):
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    _refresh_animations_enabled_from_env()
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        render.pulse_winner_glow(Seat.NORTH, reader=None)
    # No-anim short-circuit: nothing painted, baseline preserved.
    assert buf.getvalue() == ""
    assert render._last_emitted_lines == ("dummy",)
    # Restore default for other tests.
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    _refresh_animations_enabled_from_env()
