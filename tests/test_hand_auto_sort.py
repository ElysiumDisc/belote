"""3.9.4 hand auto-sort: prompt_card sorts the south hand on entry so cards
are always grouped by suit (trump first) and rank, eliminating the need to
press the manual SORT key after every deal.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from belote.deck import Suit, make_deck, shuffle
from belote.game import GameState, Phase, Seat, sort_hand
from belote.input import Key, KeyEvent


@dataclass
class ScriptedReader:
    """Minimal KeyReader stand-in that pops queued events on each read()."""
    events: Iterator[KeyEvent]

    def read(self) -> KeyEvent:
        return next(self.events)


def _state_with_unsorted_south_hand() -> GameState:
    """Build a state where SOUTH's hand is deliberately NOT in sorted order."""
    import random
    deck = shuffle(make_deck(), random.Random(99))
    hands = tuple(tuple(deck[i * 8:(i + 1) * 8]) for i in range(4))
    return GameState(
        hands=hands,
        initial_hands=hands,
        taker=Seat.SOUTH,
        trump=Suit.SPADES,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
    )


def test_prompt_card_auto_sorts_south_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    """On entry, prompt_card should call sort_south_hand so the rendered hand
    is in canonical order regardless of how cards arrived from the deal."""
    from belote.ui import prompts

    # Avoid any actual display() side-effects during the test.
    monkeypatch.setattr(prompts, "display", lambda *a, **kw: None)

    state = _state_with_unsorted_south_hand()
    original_south = state.hand_of(Seat.SOUTH)
    expected_sorted = sort_hand(original_south, state.trump)

    # Pre-condition: the deal isn't already sorted (otherwise the test is
    # vacuous). If this ever fails on a future seed, pick a different one.
    assert original_south != expected_sorted, "test seed must produce unsorted hand"

    reader = ScriptedReader(iter([KeyEvent(key=Key.ENTER, char=None)]))
    card, new_state = prompts.prompt_card(state, reader)

    assert card is not None
    assert new_state.hand_of(Seat.SOUTH) == expected_sorted, (
        "prompt_card must propagate the sorted hand"
    )
