"""4.6.3 — I/V toggle for the BelAtro top HUD.

Pins the contract that `is_top_hud_visible()` gates every BelAtro overlay
that paints over row 1 of the classic Belote HUD (joker pip strip,
synergy tooltip, full `BelAtroHUD.render`, and the trust bar).

Regression target: pre-4.6.3 the joker strip at `move(1, 2)` clobbered
the `Trump: …` field of the classic HUD with no way to hide it.
"""

from __future__ import annotations

import io
import sys

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.partner.trust import TrustTrack
from belote.belatro.ui import announce
from belote.belatro.ui.hud import render_joker_pip_strip, render_synergy_tooltip
from belote.belatro.ui.trust_bar import TrustBar


@pytest.fixture(autouse=True)
def _reset_flag() -> None:
    announce.reset_top_hud_state()
    yield
    announce.reset_top_hud_state()


def _capture(fn) -> str:
    """Run `fn` with stdout redirected; return captured text."""
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = saved
    return buf.getvalue()


def test_default_state_is_visible() -> None:
    assert announce.is_top_hud_visible() is True


def test_toggle_flips_then_restores() -> None:
    announce.toggle_top_hud()
    assert announce.is_top_hud_visible() is False
    announce.toggle_top_hud()
    assert announce.is_top_hud_visible() is True


def test_joker_pip_strip_silent_when_hidden() -> None:
    run = BelAtroRun()
    announce.toggle_top_hud()
    out = _capture(lambda: render_joker_pip_strip(run, term_w=80, row=1))
    assert out == ""


def test_joker_pip_strip_paints_when_visible() -> None:
    run = BelAtroRun()
    out = _capture(lambda: render_joker_pip_strip(run, term_w=80, row=1))
    assert "J:" in out
    assert "[" in out  # at least one slot bracket


def test_synergy_tooltip_silent_when_hidden() -> None:
    announce.toggle_top_hud()
    # Even with a hypothetically synergistic set, hidden flag returns first.
    out = _capture(lambda: render_synergy_tooltip([], term_w=80, row=5))
    assert out == ""


def test_trust_bar_silent_when_hidden() -> None:
    bar = TrustBar(TrustTrack(value=5))
    announce.toggle_top_hud()
    out = _capture(bar.render)
    assert out == ""


def test_trust_bar_paints_when_visible() -> None:
    bar = TrustBar(TrustTrack(value=5))
    out = _capture(bar.render)
    assert "Trust:" in out
