"""C1 audit fix: BelAtro consumables (Tarot / Planet) can now be activated.

Before this fix, `run.consume()` was defined but never invoked from any UI,
so Tarots and directly-bought Planets accumulated in `run.consumables` with
no way to use them. These tests pin:

1. `BelAtroRun.consume()` applies the Tarot/Planet effect and updates state.
2. `last_consumable_id` is set so Le Fou can copy the prior consumable.
3. `ConsumablesOverlay.open()` reads from `run.consumables`, dispatches to
   `run.consume()` on a digit press, and returns True on activation /
   False on empty tray or Esc.
"""

from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.planets import Mercury
from belote.belatro.items.tarots import LeChariot, LeFou, LeSoleil
from belote.belatro.ui.consumables import ConsumablesOverlay
from belote.input import Key, KeyEvent


def _stub_reader(events: Iterator[KeyEvent]) -> MagicMock:
    """Reader that returns each event in turn, then raises if over-read."""
    reader = MagicMock()
    reader.read.side_effect = events
    return reader


# ── run.consume() ───────────────────────────────────────────────────────────


def test_consume_tarot_applies_effect_and_removes_item() -> None:
    run = BelAtroRun()
    tarot = LeChariot()
    run.consumables.append(tarot)
    money_before = run.economy.money

    run.consume(tarot, context=run)

    assert run.economy.money == money_before + 5
    assert tarot not in run.consumables
    assert run.last_consumable_id == "le_chariot"


def test_consume_planet_applies_level_up() -> None:
    run = BelAtroRun()
    planet = Mercury()
    run.consumables.append(planet)

    run.consume(planet, context=run)

    assert planet not in run.consumables
    assert run.last_consumable_id == "mercury"
    assert run.contract_levels.get("diamonds") == {"add_chips": 6, "add_money": 1}


def test_le_fou_copies_last_consumable() -> None:
    """Le Fou re-applies the most-recently-consumed item's effect."""
    run = BelAtroRun()
    le_soleil = LeSoleil()
    le_fou = LeFou()
    run.consumables.extend([le_soleil, le_fou])
    money_before = run.economy.money

    run.consume(le_soleil, context=run)  # +$10
    assert run.economy.money == money_before + 10

    run.consume(le_fou, context=run)  # should re-apply Le Soleil → another +$10
    assert run.economy.money == money_before + 20
    # Le Fou is transparent: `last_consumable_id` still points at the source
    # it copied, so a second Le Fou keeps copying Le Soleil rather than itself.
    assert run.last_consumable_id == "le_soleil"


# ── ConsumablesOverlay ──────────────────────────────────────────────────────


def test_overlay_returns_false_on_empty_tray() -> None:
    run = BelAtroRun()
    reader = _stub_reader(iter([KeyEvent(Key.ENTER)]))

    overlay = ConsumablesOverlay(run, reader)
    assert overlay.open() is False


def test_overlay_activates_chosen_tarot_on_digit_press() -> None:
    run = BelAtroRun()
    run.consumables.append(LeChariot())
    money_before = run.economy.money
    reader = _stub_reader(iter([KeyEvent(Key.CHAR, "1")]))

    overlay = ConsumablesOverlay(run, reader)
    assert overlay.open() is True
    assert run.economy.money == money_before + 5
    assert not run.consumables


def test_overlay_cancels_on_esc() -> None:
    run = BelAtroRun()
    run.consumables.append(LeChariot())
    money_before = run.economy.money
    reader = _stub_reader(iter([KeyEvent(Key.ESC)]))

    overlay = ConsumablesOverlay(run, reader)
    assert overlay.open() is False
    assert run.economy.money == money_before
    assert len(run.consumables) == 1


def test_overlay_ignores_out_of_range_digit_then_picks_valid() -> None:
    run = BelAtroRun()
    run.consumables.append(LeChariot())
    money_before = run.economy.money
    # First press "9" (invalid index, ignored), then "1" (valid).
    reader = _stub_reader(
        iter([KeyEvent(Key.CHAR, "9"), KeyEvent(Key.CHAR, "1")])
    )

    overlay = ConsumablesOverlay(run, reader)
    assert overlay.open() is True
    assert run.economy.money == money_before + 5
