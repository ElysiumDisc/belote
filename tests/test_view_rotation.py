"""4.11.0: `rotate_view` — the hot-seat "draw the table from any chair" view."""

from __future__ import annotations

import random

import pytest

from belote.game import (
    Phase,
    Seat,
    legal_bids,
    legal_cards,
    new_game,
    place_bid,
    play_card,
    rotate_view,
    start_round,
    team_of,
    trick_winner_seat,
)


def _mid_play_states(seed: int) -> list:
    """Seeded states sampled through a whole round (random legal play)."""
    rng = random.Random(seed)
    state = start_round(new_game(), rng)
    while state.phase == Phase.BIDDING:
        bids = legal_bids(state)
        state = place_bid(state, rng.choice([b for b in bids if b is not None] or bids))
        if state.phase == Phase.DEAL:  # all passed
            state = start_round(state, rng)
    out = []
    while state.phase == Phase.PLAYING:
        out.append(state)
        state = play_card(state, rng.choice(legal_cards(state, state.turn)))
    return out


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("viewer", list(Seat))
def test_view_preserves_the_rules(seed: int, viewer: Seat) -> None:
    for state in _mid_play_states(seed):
        view = rotate_view(state, viewer)
        # The viewer sits at the bottom with their own hand.
        assert view.hand_of(Seat.SOUTH) == state.hand_of(viewer)
        # Same legal cards for every chair (partner/overtrump logic is relative).
        for s in Seat:
            shown = Seat((s.value - viewer.value) % 4)
            assert legal_cards(view, shown) == legal_cards(state, s)
        # Whose turn / trick winner map consistently.
        assert view.turn == Seat((state.turn.value - viewer.value) % 4)
        if state.current_trick:
            real_w = trick_winner_seat(state.current_trick, state.trump)
            view_w = trick_winner_seat(view.current_trick, view.trump)
            assert view_w == Seat((real_w.value - viewer.value) % 4)


def test_team_fields_swap_only_across_teams() -> None:
    state = _mid_play_states(3)[-1]
    from dataclasses import replace

    state = replace(state, team_scores=(120, 40), current_round_points=(30, 50))
    assert rotate_view(state, Seat.NORTH).team_scores == (120, 40)
    assert rotate_view(state, Seat.EAST).team_scores == (40, 120)
    assert rotate_view(state, Seat.WEST).current_round_points == (50, 30)
    # "NS" in the view is always the viewer's team.
    for viewer in Seat:
        view = rotate_view(state, viewer)
        assert team_of(Seat.SOUTH) == 0
        mine = state.team_scores[team_of(viewer)]
        assert view.team_scores[0] == mine


def test_south_view_is_identity() -> None:
    state = _mid_play_states(1)[2]
    assert rotate_view(state, Seat.SOUTH) is state


def test_four_rotations_round_trip() -> None:
    state = _mid_play_states(5)[4]
    view = state
    for _ in range(4):
        view = rotate_view(view, Seat.EAST)
    assert view == state
