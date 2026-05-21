"""Tests for the 4.8.0 / B2 shop purchase/reroll feedback animations.

These tests verify the helpers exist, run cleanly under BELOTE_NO_ANIM=1,
and don't perturb shop state. Visual correctness is verified by manual
walkthrough (the helpers' only side-effect is ANSI escapes on stdout).
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from belote.belatro.ui.shop import ShopScreen
from belote.ui.anim import _refresh_animations_enabled_from_env

render = sys.modules["belote.ui.render"]


class _StubShop:
    """Minimum surface for instantiating ShopScreen in tests."""

    def __init__(self):
        self.inventory = []
        self.reroll_cost = 5
        self.run = type(
            "_Run",
            (),
            {
                "economy": type("_Eco", (), {"money": 10})(),
                "tierce_charges": 0,
                "vouchers": [],
            },
        )()


def test_animate_purchase_short_circuits_under_no_anim(monkeypatch):
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    _refresh_animations_enabled_from_env()
    monkeypatch.setattr(render, "get_term_size", lambda: (80, 32))
    screen = ShopScreen(_StubShop(), reader=None)  # type: ignore[arg-type]
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        screen._animate_purchase(0, 3, money_before=10, money_after=7)
    # No painting under no-anim; baseline preserved.
    assert buf.getvalue() == ""
    assert render._last_emitted_lines == ("dummy",)
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    _refresh_animations_enabled_from_env()


def test_animate_reroll_short_circuits_under_no_anim(monkeypatch):
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    _refresh_animations_enabled_from_env()
    monkeypatch.setattr(render, "get_term_size", lambda: (80, 32))
    screen = ShopScreen(_StubShop(), reader=None)  # type: ignore[arg-type]
    render._last_emitted_lines = ("dummy",)
    buf = io.StringIO()
    with redirect_stdout(buf):
        screen._animate_reroll(3)
    assert buf.getvalue() == ""
    assert render._last_emitted_lines == ("dummy",)
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    _refresh_animations_enabled_from_env()
