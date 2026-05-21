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


def test_belatro_hud_render_writes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.7.3: BelAtroHUD.render must batch the pip strip, summary rows,
    score line, joker list, tally readout, and synergy tooltip into a
    SINGLE sys.stdout.write call. Pre-4.7.3 the pip strip and synergy
    tooltip each did their own write+flush, costing 2–3 syscalls per HUD
    refresh.

    Same single-write convention as ShopScreen._render (pinned in
    test_render_diff.py::test_shop_render_writes_once_per_frame).
    """
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.ui.hud import BelAtroHUD
    from belote.game import new_game

    register_all_items()
    run = BelAtroRun(seed=1)
    h = BelAtroHUD(run)
    acc = ScoreAccumulator()
    state = new_game()
    acc.trigger_round_start(state)

    class _CountingBuf(io.StringIO):
        write_count = 0

        def write(self, s: str) -> int:  # type: ignore[override]
            self.write_count += 1
            return super().write(s)

    buf = _CountingBuf()
    saved = sys.stdout
    sys.stdout = buf
    try:
        # `get_term_size` is imported locally inside BelAtroHUD.render from
        # `belote.ui.render`; patch the source module so both that import and
        # the `_render_compact` fallback see the deterministic size.
        render_mod = sys.modules["belote.ui.render"]
        monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))
        h.render(acc, state)
    finally:
        sys.stdout = saved

    assert buf.write_count == 1, (
        f"BelAtroHUD.render must batch into one write; got {buf.write_count}. "
        f"Pre-4.7.3 this was 2–3 due to the pip-strip / tooltip helpers "
        f"writing independently."
    )
