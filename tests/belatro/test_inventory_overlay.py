"""4.7.0 follow-up: InventoryOverlay (V key) tests.

Covers entry construction (joker/voucher/consumable/permanent/contract
levels rows), navigation, detail-view drill-down, and exit semantics.
The detail page text is exercised at the strings-in-output level — we
don't pin exact ANSI sequences because color codes drift with theme
changes, only the visible content.
"""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.partner.partner_state import PartnerState
from belote.belatro.ui.inventory import (
    InventoryOverlay,
    _build_entries,
)
from belote.input import Key, KeyEvent


def _make_run() -> BelAtroRun:
    return BelAtroRun(seed=1, deck_id="le_classique", partner=PartnerState())


class _ScriptedReader:
    """Reader that returns a fixed sequence of KeyEvents."""

    def __init__(self, events: list[KeyEvent]) -> None:
        self._events = list(events)

    def read(self) -> KeyEvent:
        if not self._events:
            return KeyEvent(Key.EOF)
        return self._events.pop(0)

    def read_timeout(self, _t: float) -> KeyEvent | None:
        if not self._events:
            return None
        return self._events.pop(0)


# ── entry building ──


def test_build_entries_empty_run_returns_empty_list() -> None:
    run = _make_run()
    entries = _build_entries(run)
    assert entries == []


def test_build_entries_includes_joker_with_edition_tag() -> None:
    """A joker with an Edition.FOIL should show `[Foil]` in its title."""
    from belote.belatro.items.base import Edition
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    joker = TierceCharger()
    joker.edition = Edition.FOIL
    run.jokers.append(joker)

    entries = _build_entries(run)
    assert any(e.category == "JOKERS" and "[Foil]" in e.title for e in entries)


def test_build_entries_includes_permanent_bonuses_when_set() -> None:
    run = _make_run()
    run.permanent_chips = 50
    run.permanent_mult = 1.2

    entries = _build_entries(run)
    perm = [e for e in entries if e.category == "PERMANENT BONUSES"]
    assert len(perm) == 1
    assert "+50 chips" in perm[0].title
    assert "×1.20" in perm[0].title


def test_build_entries_skips_permanent_bonuses_when_unchanged() -> None:
    """Fresh run with no tarot bumps → no permanent bonuses row."""
    run = _make_run()
    entries = _build_entries(run)
    assert not any(e.category == "PERMANENT BONUSES" for e in entries)


def test_build_entries_includes_contract_levels() -> None:
    run = _make_run()
    run.contract_levels["hearts"] = {"add_mult": 0.3, "add_chips": 10}

    entries = _build_entries(run)
    cl = [e for e in entries if e.category == "CONTRACT LEVELS"]
    assert len(cl) == 1
    assert cl[0].title == "hearts"
    # Detail body should mention both bumps.
    body = " ".join(cl[0].detail_lines)
    assert "+0.3 Mult/trick" in body
    assert "+10 chips/trick" in body


# ── overlay open() — empty path ──


def test_open_empty_returns_immediately_on_esc(capsys) -> None:
    run = _make_run()
    reader = _ScriptedReader([KeyEvent(Key.ESC)])
    InventoryOverlay(run, reader).open()
    out = capsys.readouterr().out
    assert "no items owned" in out.lower() or "no items" in out.lower()


def test_open_empty_invalidates_diff() -> None:
    import sys

    render_module = sys.modules["belote.ui.render"]
    render_module._last_emitted_lines = ("sentinel",)

    run = _make_run()
    reader = _ScriptedReader([KeyEvent(Key.ESC)])
    InventoryOverlay(run, reader).open()
    assert render_module._last_emitted_lines is None


# ── overlay open() — list view ──


def test_open_list_view_esc_closes(capsys) -> None:
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    reader = _ScriptedReader([KeyEvent(Key.ESC)])
    InventoryOverlay(run, reader).open()
    out = capsys.readouterr().out
    assert "INVENTORY" in out
    assert "JOKERS" in out


def test_open_list_view_v_closes_too() -> None:
    """V (the same key that opens the overlay) also closes it — toggle ergonomic."""
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    reader = _ScriptedReader([KeyEvent(Key.INVENTORY)])
    InventoryOverlay(run, reader).open()  # must not loop forever


def test_open_navigates_with_arrow_keys() -> None:
    """Down → next entry; selection wraps around."""
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    run.jokers.append(TierceCharger())
    # Three reads: DOWN moves selection, DOWN again, then ESC closes.
    reader = _ScriptedReader([
        KeyEvent(Key.DOWN),
        KeyEvent(Key.DOWN),
        KeyEvent(Key.ESC),
    ])
    InventoryOverlay(run, reader).open()  # exits cleanly


def test_open_enter_opens_detail_view_then_esc_returns(capsys) -> None:
    """ENTER drills into detail; ESC pops back to list; second ESC closes."""
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    reader = _ScriptedReader([
        KeyEvent(Key.ENTER),  # open detail
        KeyEvent(Key.ESC),    # back to list
        KeyEvent(Key.ESC),    # close overlay
    ])
    InventoryOverlay(run, reader).open()
    out = capsys.readouterr().out
    # Both list and detail headers should have rendered at least once.
    assert "INVENTORY" in out
    assert "back to list" in out  # detail view footer hint


def test_open_eof_during_list_closes_safely() -> None:
    """A scripted EOF (closed stdin) must terminate the loop, not spin."""
    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    reader = _ScriptedReader([])  # empty → EOF on first read
    InventoryOverlay(run, reader).open()


def test_open_invalidates_diff_on_normal_exit() -> None:
    import sys

    render_module = sys.modules["belote.ui.render"]
    render_module._last_emitted_lines = ("sentinel",)

    from belote.belatro.items.jokers.annonces import TierceCharger

    run = _make_run()
    run.jokers.append(TierceCharger())
    reader = _ScriptedReader([KeyEvent(Key.ESC)])
    InventoryOverlay(run, reader).open()
    assert render_module._last_emitted_lines is None
