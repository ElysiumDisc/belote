"""Tests for `ScoreAccumulator` handler-index drift detection (4.8.2 B3).

Pre-4.8.2 the lazy-build gate in `_fire_jokers` was
`if not self._handler_index and self._jokers`, which is False once
`attach_jokers([])` has run (the index dict has 5 truthy keys with empty
lists). Tests that appended to `acc._jokers` after attaching an empty list
were silently ignored.

The fix replaces the gate with an identity-set comparison against the
joker set captured at the most recent `attach_jokers` call.
"""

from __future__ import annotations

from typing import Any

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.belatro.items.base import Joker, JokerResult
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Seat


class _CountingJoker(Joker):
    id = "_test_counter"
    name = "Counter"
    description = "test stub: +1 chip per trick"
    cost = 0

    def on_trick_won(
        self, event: TrickWonEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        return JokerResult(add_chips=1)


def _make_trick_event() -> TrickWonEvent:
    cards = (Card(Suit.SPADES, Rank.SEVEN),)
    return TrickWonEvent(
        winner=Seat.SOUTH,
        cards=cards,
        trick_number=1,
        is_last=False,
        card_points=0,
        trump=Suit.SPADES,
        leader_seat=Seat.SOUTH,
    )


def _make_state() -> GameState:
    return GameState(hands=((), (), (), ()), trump=Suit.SPADES, taker=Seat.SOUTH)


def test_attach_empty_then_append_triggers_rebuild() -> None:
    """The B3 regression: `attach_jokers([])` then `acc._jokers.append(...)`
    must fire the new joker's handler on the next event. Pre-4.8.2 it
    silently did not.
    """
    acc = ScoreAccumulator()
    acc.attach_jokers([])  # pre-fix: this poisons the lazy-build gate
    state = acc.trigger_round_start(_make_state())

    joker = _CountingJoker()
    acc._jokers.append(joker)  # post-attach mutation

    acc.process_event(state, _make_trick_event())
    # Without B3 fix: chips stay at 0 (joker handler never fired).
    # With B3 fix: handler runs, +1 chip.
    assert acc._ledger is not None
    assert acc._ledger.chips >= 1, (
        f"Joker appended after attach_jokers([]) did not fire. "
        f"chips={acc._ledger.chips} (expected ≥1)."
    )


def test_attach_then_replace_triggers_rebuild() -> None:
    """Replacing the joker list (different joker object) must also rebuild."""
    acc = ScoreAccumulator()
    initial = _CountingJoker()
    acc.attach_jokers([initial])
    state = acc.trigger_round_start(_make_state())

    # Replace with a different joker instance — id() differs.
    replacement = _CountingJoker()
    acc._jokers = [replacement]

    acc.process_event(state, _make_trick_event())
    # Handler must still fire (rebuild picks up the new instance).
    assert acc._ledger is not None
    assert acc._ledger.chips >= 1


def test_no_drift_no_rebuild_overhead() -> None:
    """Sanity: when `_jokers` is stable, repeated `process_event` calls
    should NOT trigger a rebuild (which would be wasted work)."""
    acc = ScoreAccumulator()
    joker = _CountingJoker()
    acc.attach_jokers([joker])
    state = acc.trigger_round_start(_make_state())

    # Snapshot the index identity. After a rebuild it would be a new dict.
    index_before = acc._handler_index

    for _ in range(5):
        acc.process_event(state, _make_trick_event())

    # No rebuild expected — `_handler_index` should be the same dict object.
    assert acc._handler_index is index_before, (
        "Handler index was rebuilt despite stable `_jokers`. "
        "Drift detection should be a no-op in the happy path."
    )
