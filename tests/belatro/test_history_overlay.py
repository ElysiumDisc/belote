"""3.3.0: BelAtro [H] history overlay.

The classic Belote H-key overlay reads ``state.score_history``, but
``BelAtro.engine.round_driver.drive_round`` never calls
``apply_round_score`` (the sole writer of ``score_history``), so without
this wiring the overlay always showed "No rounds completed yet." in
BelAtro. These tests pin the new mechanism:

1. ``BelAtroRun.history`` is a list (empty by default) of entries that
   carry the BelAtro-specific context the classic schema can't.
2. ``_record_history_entry`` correctly classifies WON / FAILED /
   CAPOT / SURVIVED status, captures boss + taker + contract, and
   computes the money delta.
3. ``set_history_override`` swaps the H-key renderer at run scope and
   clears back to the classic path on exit.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.main import BelAtroGame
from belote.deck import Suit
from belote.game import Seat, new_game
from belote.scoring import ScoringBreakdown
from belote.ui import prompts as prompts_module


def _bd(
    *,
    taker_team: int = 0,
    taker_total: int = 120,
    defender_total: int = 62,
    is_failed: bool = False,
    is_capot: bool = False,
    tricks_ns: int = 5,
    tricks_ew: int = 3,
) -> ScoringBreakdown:
    return ScoringBreakdown(
        taker_team=taker_team,
        table_taker_pts=taker_total,
        table_defender_pts=defender_total,
        credit_taker_pts=taker_total,
        credit_defender_pts=defender_total,
        last_trick_team=0,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=taker_total,
        defender_total=defender_total,
        is_capot=is_capot,
        is_failed=is_failed,
        tricks_ns=tricks_ns,
        tricks_ew=tricks_ew,
    )


def _game_with_run() -> BelAtroGame:
    g = BelAtroGame()
    g.run = BelAtroRun()
    return g


def test_belatro_run_starts_with_empty_history() -> None:
    """Default-constructed runs ship with `history = []`, ready to grow."""
    run = BelAtroRun()
    assert run.history == []


def test_record_history_entry_won() -> None:
    g = _game_with_run()
    assert g.run is not None
    final_state = dataclasses.replace(
        new_game(),
        contract="normal",
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
    )
    g._record_history_entry(
        ante=2,
        blind_index=1,
        target=150,
        boss=None,
        final_state=final_state,
        bd=_bd(taker_total=180),
        total=180,
        money_delta=5,
        survived_via_insurance=False,
    )
    entry = g.run.history[-1]
    assert entry.ante == 2
    assert entry.blind_label == "Big"
    assert entry.target == 150
    assert entry.boss_name is None
    assert entry.taker_label == "S (NS)"
    assert entry.contract == Suit.HEARTS.symbol
    assert entry.score == 180
    assert entry.status == "WON"
    assert entry.money_delta == 5
    assert entry.tricks_ns == 5
    assert entry.tricks_ew == 3


def test_record_history_entry_failed_marks_failure() -> None:
    g = _game_with_run()
    assert g.run is not None
    g._record_history_entry(
        ante=1,
        blind_index=0,
        target=100,
        boss=None,
        final_state=dataclasses.replace(new_game(), contract=None, trump=None),
        bd=_bd(taker_total=80, is_failed=True),
        total=80,
        money_delta=0,
        survived_via_insurance=False,
    )
    assert g.run.history[-1].status == "FAILED"
    assert g.run.history[-1].taker_label == "—"
    assert g.run.history[-1].contract == "—"


def test_record_history_entry_survived_via_insurance() -> None:
    g = _game_with_run()
    assert g.run is not None
    g._record_history_entry(
        ante=3,
        blind_index=2,
        target=600,
        boss=MagicMock(name="L'Avocat"),
        final_state=dataclasses.replace(
            new_game(), contract="sans_atout", trump=None, taker=Seat.NORTH
        ),
        bd=_bd(taker_total=400, is_failed=True),
        total=400,
        money_delta=-2,
        survived_via_insurance=True,
    )
    entry = g.run.history[-1]
    assert entry.status == "SURVIVED"
    assert entry.blind_label == "Boss"
    # MagicMock's `.name` is a string-like attribute; the renderer just stringifies it
    assert entry.boss_name is not None
    assert entry.contract == "SA"


def test_record_history_entry_capot_promotes_status() -> None:
    g = _game_with_run()
    assert g.run is not None
    final_state = dataclasses.replace(
        new_game(),
        contract="tout_atout",
        trump=Suit.TOUT_ATOUT,
        taker=Seat.SOUTH,
    )
    g._record_history_entry(
        ante=4,
        blind_index=0,
        target=300,
        boss=None,
        final_state=final_state,
        bd=_bd(taker_total=500, is_capot=True, tricks_ns=8, tricks_ew=0),
        total=500,
        money_delta=8,
        survived_via_insurance=False,
    )
    entry = g.run.history[-1]
    assert entry.status == "CAPOT"
    assert entry.contract == "TA"
    assert entry.tricks_ns == 8 and entry.tricks_ew == 0


def test_history_override_routes_h_key_and_clears() -> None:
    """`set_history_override` must redirect `show_history` to the BelAtro
    renderer, and `set_history_override(None)` must restore the classic
    `state.score_history` path so post-BelAtro classic plays still work.
    """
    state = new_game()
    reader = MagicMock()
    called: list[str] = []

    prompts_module.set_history_override(lambda _r: called.append("belatro"))
    try:
        prompts_module.show_history(state, reader)
    finally:
        prompts_module.set_history_override(None)

    assert called == ["belatro"]
    # The reader was never touched on the BelAtro path — the override
    # short-circuits before the classic loop that calls reader.read().
    reader.read.assert_not_called()


def test_history_override_cleared_falls_through_to_classic_empty_path() -> None:
    """With no override and an empty score_history, the classic overlay
    short-circuits on its first key read showing 'No rounds completed yet.'.
    We only need to assert it actually called into the classic path."""
    state = new_game()  # score_history defaults to ()
    reader = MagicMock()
    # First reader.read() returns "any key" → classic show_history returns.
    reader.read.return_value = MagicMock(key=MagicMock(name="ENTER"))

    prompts_module.set_history_override(None)
    prompts_module.show_history(state, reader)

    reader.read.assert_called()  # classic loop *does* read at least once


@pytest.fixture(autouse=True)
def _isolate_history_override() -> Any:
    """Every test starts with a cleared override; tearDown restores."""
    prompts_module.set_history_override(None)
    yield
    prompts_module.set_history_override(None)
