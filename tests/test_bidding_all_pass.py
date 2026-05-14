"""All-pass bidding edge cases.

`test_new_coverage.py::test_all_pass_redeal` covers the happy-path 8-pass
redeal at a basic level. These tests pin the deeper invariants the C2 audit
finding flagged: full state reset, multi-redeal stability, and that the
re-dealt round bids cleanly.
"""

from __future__ import annotations

import random

from belote.deck import Suit
from belote.game import (
    Phase,
    Seat,
    new_game,
    process_bid,
    start_round,
)


def test_all_pass_full_state_reset() -> None:
    """After 8 passes the bidding state machine must reset every field that
    affects the next round, not just `phase` and `dealer`."""
    state = new_game()
    state = start_round(state, random.Random(7))

    for _ in range(8):
        state = process_bid(state, None)

    assert state.phase == Phase.DEAL
    assert state.bids == ()
    assert state.bidder_index == 0
    assert state.bidding_round == 1
    # Belote/declaration trackers should be in their initial state — no stale
    # carry-over from a prior aborted bid sequence.
    assert state.trump is None
    assert state.taker is None


def test_all_pass_twice_in_a_row_advances_dealer_twice() -> None:
    """Two consecutive all-pass redeals — confirms the dealer rotation isn't
    accidentally double-applied or skipped."""
    state = new_game()
    state = start_round(state, random.Random(11))
    dealer0 = state.dealer

    # First redeal
    for _ in range(8):
        state = process_bid(state, None)
    assert state.phase == Phase.DEAL
    assert state.dealer == dealer0.next_seat()

    # Re-enter the round; second redeal
    state = start_round(state, random.Random(13))
    for _ in range(8):
        state = process_bid(state, None)
    assert state.phase == Phase.DEAL
    assert state.dealer == dealer0.next_seat().next_seat()


def test_round_2_all_pass_falls_back_to_redeal_not_to_round_3() -> None:
    """Belote has only two bidding rounds. The implementation must not produce
    a `bidding_round == 3` state under any combination of passes."""
    state = new_game()
    state = start_round(state, random.Random(17))

    # 4 passes → round 2 (no redeal yet)
    for _ in range(4):
        state = process_bid(state, None)
    assert state.bidding_round == 2

    # 4 more passes → redeal, NOT round 3
    for _ in range(4):
        state = process_bid(state, None)
    assert state.phase == Phase.DEAL
    assert state.bidding_round == 1  # reset back to 1 for the next deal


def test_redeal_then_successful_bid_round_completes_normally() -> None:
    """After an all-pass redeal, the next deal must be playable end-to-end —
    no leftover state breaks the new bidding round."""
    state = new_game()
    state = start_round(state, random.Random(19))

    for _ in range(8):
        state = process_bid(state, None)
    assert state.phase == Phase.DEAL

    # New deal, then a successful bid
    state = start_round(state, random.Random(23))
    assert state.phase == Phase.BIDDING
    assert state.bidder_index == 0
    state = process_bid(state, Suit.HEARTS)
    assert state.phase == Phase.PLAYING
    assert state.trump == Suit.HEARTS
    # Taker is the seat that bid — first bidder after the new dealer.
    assert state.taker is not None
    assert state.taker == state.dealer.next_seat()


def test_all_pass_at_each_starting_dealer() -> None:
    """Dealer rotation should work symmetrically from any starting seat."""
    for seed in (1, 2, 3, 4):
        state = new_game()
        state = start_round(state, random.Random(seed))
        dealer_before = state.dealer
        for _ in range(8):
            state = process_bid(state, None)
        assert state.dealer == dealer_before.next_seat(), (
            f"seed={seed}: dealer didn't advance from {dealer_before}"
        )
        assert state.dealer in (Seat.SOUTH, Seat.WEST, Seat.NORTH, Seat.EAST)
