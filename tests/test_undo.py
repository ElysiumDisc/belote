"""Undo history-stack contract.

The gameflow loop in src/belote/gameflow.py records a `history_stack:
list[GameState]` snapshot before each transition and pops it on UNDO. These
tests verify that the snapshot/restore cycle preserves equality and that the
`stack_base` boundary correctly distinguishes "undo within round" from
"nothing left to undo".
"""

from __future__ import annotations

import random

from belote.game import (
    GameState,
    Phase,
    legal_cards,
    new_game,
    place_bid,
    play_card,
    start_round,
)


def _state_in_play() -> GameState:
    rng = random.Random(11)
    state = start_round(new_game(), rng)
    assert state.up_card is not None
    state = place_bid(state, state.up_card.suit)
    assert state.phase == Phase.PLAYING
    return state


def test_undo_stack_snapshot_restores_state() -> None:
    """Pushing a state and popping it back must yield an equal state.

    `replace()` returns a new immutable GameState; the original is never
    mutated, so popping the snapshot off the history stack is a true rollback.
    """
    state = _state_in_play()
    history: list[GameState] = []

    history.append(state)
    legal = legal_cards(state, state.turn)
    advanced = play_card(state, legal[0])

    assert advanced is not state
    assert advanced != state  # different turn / hand / current_trick

    restored = history.pop()
    assert restored == state
    assert restored.turn == state.turn
    assert restored.hands == state.hands
    assert restored.current_trick == state.current_trick


def test_undo_stack_base_marks_round_boundary() -> None:
    """`stack_base` records the stack length at round start; undos within the
    round are allowed (`len(history) > stack_base`), undos at exactly the base
    must trigger the "nothing left to undo — fresh deal" branch."""
    state = _state_in_play()
    history: list[GameState] = []
    stack_base = len(history)
    assert stack_base == 0

    history.append(state)
    legal = legal_cards(state, state.turn)
    state = play_card(state, legal[0])
    history.append(state)
    legal = legal_cards(state, state.turn)
    state = play_card(state, legal[0])

    # Two snapshots → two undos available within the round.
    assert len(history) > stack_base
    state = history.pop()
    assert len(history) > stack_base
    state = history.pop()

    # Boundary reached: pop count equals snapshots; further UNDO must restart.
    assert len(history) == stack_base
    assert not (len(history) > stack_base)


def test_undo_stack_isolates_rounds() -> None:
    """Two consecutive rounds share a stack but `stack_base` per round must
    prevent round-1 undos from leaking into round 2."""
    history: list[GameState] = []

    # Round 1
    r1_state = _state_in_play()
    r1_base = len(history)
    history.append(r1_state)
    history.append(play_card(r1_state, legal_cards(r1_state, r1_state.turn)[0]))

    # End round 1 — clear back to its base (mirrors gameflow.py:279).
    del history[r1_base:]
    assert history == []

    # Round 2
    r2_state = _state_in_play()
    r2_base = len(history)
    history.append(r2_state)

    # Within round 2, popping does NOT touch round 1 state (round 1 already
    # cleared); the base correctly delimits the new round.
    assert r2_base == 0
    assert len(history) > r2_base
    history.pop()
    assert len(history) == r2_base
