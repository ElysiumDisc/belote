"""
4.7.0: Slot-machine tally animation tests.

Covers diff invalidation, hide_hud suppression, skip-on-keypress, and the
module-level `_last_tally_total` cache lifecycle. The visual output is
intentionally not asserted character-by-character — we only verify the
behavioral contracts (invalidate_diff fires; hide_hud renders nothing;
cache is reset cleanly).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.ui import announce as announce_module
from belote.belatro.ui.announce import BelAtroAnnounce, reset_tally_state
from belote.game import BossModifiers, GameState
from belote.input import Key, KeyEvent


class _FakeReader:
    """Reader stub that always reports SPACE (immediate skip). Mirrors the
    pattern in tests/test_alt_screen_scroll.py."""

    def read(self) -> KeyEvent:
        return KeyEvent(Key.SPACE)

    def read_timeout(self, _t: float) -> KeyEvent | None:
        return KeyEvent(Key.SPACE)


class _NeverPressReader:
    """Reader stub that never sends a key — animation runs full duration."""

    def read(self) -> KeyEvent:
        return KeyEvent(Key.CHAR, "")

    def read_timeout(self, _t: float) -> KeyEvent | None:
        return None


def _make_acc_and_state(
    *,
    chips: int = 50,
    mult: float = 2.0,
    target: int = 100,
    boss: BossModifiers | None = None,
) -> tuple[ScoreAccumulator, GameState]:
    acc = ScoreAccumulator()
    acc.target_score = target
    state = GameState(hands=((), (), (), ()), _chips=chips, _mult=mult)
    if boss is not None:
        state = replace(state, boss_modifiers=boss)
    state = acc.trigger_round_start(state)
    return acc, state


# ── diff-baseline contract ──


def test_slot_machine_invalidates_diff_baseline() -> None:
    """The 4.6.4 architectural rule: any overlay that paints rows directly
    must invalidate the diff baseline so subsequent display() calls re-emit
    overwritten rows."""
    # `belote.ui.__init__` re-exports `render` (the function), shadowing
    # the submodule name in the `belote.ui` namespace. To poke at the
    # module's globals (`_last_emitted_lines`), reach into sys.modules
    # directly. Mirrors the trick used in `test_animate_score_update_*`
    # at tests/test_alt_screen_scroll.py.
    import sys

    render_module = sys.modules["belote.ui.render"]

    reset_tally_state()
    acc, state = _make_acc_and_state()

    # Prime the diff baseline with sentinel content (typed as `tuple[str, ...]`
    # in the module; a tuple is the natural fixture).
    render_module._last_emitted_lines = ("sentinel",)

    BelAtroAnnounce.slot_machine_tally(acc, state, _FakeReader(), points=10)

    assert render_module._last_emitted_lines is None, (
        "slot_machine_tally must invalidate_diff() in its finally block"
    )


# ── hide_hud suppression ──


def test_slot_machine_under_hide_hud_renders_nothing(capsys) -> None:
    """Le Brouillard's `hide_hud=True` should suppress the animation entirely
    so the boss's 'hide the score' promise holds."""
    reset_tally_state()
    acc, state = _make_acc_and_state(boss=BossModifiers(hide_hud=True))

    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)
    captured = capsys.readouterr()

    # Should be empty — no ANSI move sequences, no glyphs.
    assert captured.out == "", (
        f"hide_hud must suppress the animation; got output: {captured.out!r}"
    )


def test_slot_machine_under_hide_hud_still_updates_cache() -> None:
    """Even when suppressed, the cache must update so a subsequent visible
    call animates from the correct previous total (otherwise the next animation
    rolls from an old value)."""
    reset_tally_state()
    acc, state = _make_acc_and_state(chips=80, mult=1.5)  # total = 120

    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)
    assert announce_module._last_tally_total == 120


def test_slot_machine_under_separate_scoring_renders_nothing(capsys) -> None:
    """La Compétition's running total (sum) diverges from the round's sealed
    total (per-seat max). The animation must skip rather than mislead the
    player. Mirrors the HUD's `separate_scoring` gate at belatro/ui/hud.py."""
    reset_tally_state()
    acc, state = _make_acc_and_state(boss=BossModifiers(separate_scoring=True))

    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)
    captured = capsys.readouterr()

    assert captured.out == "", (
        f"separate_scoring must suppress the animation; got: {captured.out!r}"
    )


def test_slot_machine_under_separate_scoring_still_updates_cache() -> None:
    reset_tally_state()
    acc, state = _make_acc_and_state(
        chips=90, mult=2.0,  # total = 180
        boss=BossModifiers(separate_scoring=True),
    )
    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)
    assert announce_module._last_tally_total == 180


def test_slot_machine_tiny_terminal_renders_nothing(capsys, monkeypatch) -> None:
    """When term_h < 6, the row math (term_h - 5, -4, -3) collides with
    HUD row 1. Skip the animation entirely on undersized terminals."""
    # `belote.ui.render` is shadowed by the re-exported function in
    # `belote/ui/__init__.py`; reach the module via sys.modules. See the
    # invalidate-diff test above for the same trick.
    import sys

    render_module = sys.modules["belote.ui.render"]
    monkeypatch.setattr(render_module, "get_term_size", lambda: (80, 4))

    reset_tally_state()
    acc, state = _make_acc_and_state(chips=50, mult=2.0)
    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)

    captured = capsys.readouterr()
    assert captured.out == "", (
        f"tiny terminal (term_h<6) must suppress the animation; got: {captured.out!r}"
    )


# ── 4.7.0 follow-up: persistent readout (folded into HUD) ──


def test_slot_machine_stores_final_readout_for_hud_repaint() -> None:
    """After a successful animation, `_last_tally_readout` holds the two
    lines (bucket + odometer) the HUD will repaint between tricks."""
    reset_tally_state()
    assert announce_module._last_tally_readout is None
    acc, state = _make_acc_and_state(chips=80, mult=2.0)

    BelAtroAnnounce.slot_machine_tally(acc, state, _FakeReader(), points=15)

    readout = announce_module._last_tally_readout
    assert readout is not None
    assert len(readout) == 2  # bucket + odometer
    # Final total should appear in at least one line (the odometer).
    assert any("160" in line for line in readout)


def test_reset_tally_state_clears_readout() -> None:
    """reset_tally_state must clear BOTH the total cache AND the readout
    cache — leftover readout from a prior round would otherwise paint in
    the new round's HUD before the first trick fires."""
    announce_module._last_tally_total = 999
    announce_module._last_tally_readout = ["stale-bucket", "stale-odometer"]
    reset_tally_state()
    assert announce_module._last_tally_total is None
    assert announce_module._last_tally_readout is None


def test_slot_machine_under_hide_hud_does_not_store_readout() -> None:
    """When Le Brouillard suppresses the animation, the readout cache
    must also stay None so the HUD doesn't paint a stale row."""
    reset_tally_state()
    acc, state = _make_acc_and_state(boss=BossModifiers(hide_hud=True))

    BelAtroAnnounce.slot_machine_tally(acc, state, _NeverPressReader(), points=10)
    assert announce_module._last_tally_readout is None


def test_hud_paints_persistent_tally_when_visible(capsys) -> None:
    """`BelAtroHUD.render()` paints `_last_tally_readout` near the bottom
    of the terminal when the top HUD is visible. Pressing I (which
    toggles `_top_hud_visible`) suppresses the render via the same
    early-return path; that part is exercised by the existing top-HUD
    toggle test."""
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.partner.partner_state import PartnerState
    from belote.belatro.ui.hud import BelAtroHUD

    reset_tally_state()
    # Seed the readout directly — no need to run the full animation.
    announce_module._last_tally_readout = [
        "TEST-BUCKET-LINE",
        "TEST-ODOMETER-LINE",
    ]

    run = BelAtroRun(seed=1, deck_id="le_classique", partner=PartnerState())
    hud = BelAtroHUD(run)
    acc, state = _make_acc_and_state(chips=50, mult=2.0)
    hud.render(acc, state)
    out = capsys.readouterr().out

    assert "TEST-BUCKET-LINE" in out
    assert "TEST-ODOMETER-LINE" in out


def test_hud_does_not_paint_readout_when_top_hud_hidden(capsys) -> None:
    """Toggling the top HUD off must also hide the persistent tally —
    `BelAtroHUD.render` early-returns when `is_top_hud_visible()` is
    False, so the readout never paints."""
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.partner.partner_state import PartnerState
    from belote.belatro.ui.announce import reset_top_hud_state, toggle_top_hud
    from belote.belatro.ui.hud import BelAtroHUD

    reset_tally_state()
    reset_top_hud_state()  # ensure starting visible
    announce_module._last_tally_readout = [
        "SHOULD-NOT-APPEAR-BUCKET",
        "SHOULD-NOT-APPEAR-ODOMETER",
    ]
    toggle_top_hud()  # hide

    try:
        run = BelAtroRun(seed=1, deck_id="le_classique", partner=PartnerState())
        hud = BelAtroHUD(run)
        acc, state = _make_acc_and_state()
        hud.render(acc, state)
        out = capsys.readouterr().out
        assert "SHOULD-NOT-APPEAR" not in out
    finally:
        reset_top_hud_state()  # restore for sibling tests


def test_slot_machine_cache_updates_even_if_render_raises(monkeypatch) -> None:
    """Audit critical: a render-time exception (KeyboardInterrupt or other)
    must not leave the cache stale, otherwise the next round's first animation
    rolls from an obsolete previous-total. The cache update lives in the
    `finally` block."""
    reset_tally_state()
    announce_module._last_tally_total = 50  # pretend a previous round ran
    acc, state = _make_acc_and_state(chips=100, mult=2.0)  # new total = 200

    class _RaisingReader:
        def read(self) -> KeyEvent:
            raise KeyboardInterrupt

        def read_timeout(self, _t: float) -> KeyEvent | None:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        BelAtroAnnounce.slot_machine_tally(
            acc, state, _RaisingReader(), points=10
        )

    # Cache should still reflect the new total — finally block ran.
    assert announce_module._last_tally_total == 200


# ── cache lifecycle ──


def test_reset_tally_state_clears_cache() -> None:
    announce_module._last_tally_total = 999
    reset_tally_state()
    assert announce_module._last_tally_total is None


def test_slot_machine_updates_cache_to_current_total() -> None:
    reset_tally_state()
    acc, state = _make_acc_and_state(chips=100, mult=3.0)  # total = 300

    BelAtroAnnounce.slot_machine_tally(acc, state, _FakeReader(), points=10)
    assert announce_module._last_tally_total == 300


# ── skip-on-keypress ──


def test_slot_machine_skips_on_keypress_without_crash() -> None:
    """A SPACE keypress mid-animation must short-circuit to the final frame
    without crashing or leaving stale state."""
    reset_tally_state()
    acc, state = _make_acc_and_state(chips=50, mult=2.0)

    # Should complete without raising. The _FakeReader returns SPACE on the
    # first read_timeout call.
    BelAtroAnnounce.slot_machine_tally(acc, state, _FakeReader(), points=10)

    # Cache should still reflect the final total (skip jumps to final frame).
    assert announce_module._last_tally_total == 100


@pytest.mark.parametrize("skip_key", [Key.SPACE, Key.ESC, Key.ENTER, Key.EOF])
def test_slot_machine_each_skip_key_works(skip_key: Key) -> None:
    class _SingleSkipReader:
        def read(self) -> KeyEvent:
            return KeyEvent(skip_key)

        def read_timeout(self, _t: float) -> KeyEvent | None:
            return KeyEvent(skip_key)

    reset_tally_state()
    acc, state = _make_acc_and_state()
    # Just verifying no crash on each accepted skip key.
    BelAtroAnnounce.slot_machine_tally(
        acc, state, _SingleSkipReader(), points=10
    )


# ── deterministic painting contract ──


def test_slot_machine_paints_total_at_end(capsys) -> None:
    """The final frame must render the new total exactly."""
    reset_tally_state()
    acc, state = _make_acc_and_state(chips=42, mult=2.0)  # total = 84

    BelAtroAnnounce.slot_machine_tally(acc, state, _FakeReader(), points=10)
    out = capsys.readouterr().out

    # The odometer line renders the final total `84` somewhere in the
    # output. We don't assert position — only that the value appears at
    # least once (because intermediate eased frames may also include it).
    assert "84" in out
