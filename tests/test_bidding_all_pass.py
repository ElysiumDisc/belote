"""All-pass bidding edge cases.

`test_new_coverage.py::test_all_pass_redeal` covers the happy-path 8-pass
redeal at a basic level. These tests pin the deeper invariants the C2 audit
finding flagged: full state reset, multi-redeal stability, and that the
re-dealt round bids cleanly.
"""

from __future__ import annotations

import random
from dataclasses import replace

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


def test_litige_pool_survives_all_pass_redeal() -> None:
    """A pending litige pool must persist across an all-pass redeal. The
    redeal does not call `apply_round_score`, so it cannot zero the pool;
    `reset_round_fields` is explicitly contracted not to touch
    `litige_points`. Only a non-litige scoring round consumes the pool.
    """
    state = new_game()
    state = start_round(state, random.Random(29))
    # Simulate a prior litige round having left 92 pts in the pool.
    state = replace(state, litige_points=92)
    assert state.litige_points == 92

    # All-pass the current bidding round → forced redeal.
    for _ in range(8):
        state = process_bid(state, None)
    assert state.phase == Phase.DEAL
    assert state.litige_points == 92, (
        "Pending litige pool was zeroed by all-pass; it must survive until "
        "the next non-litige scoring round consumes it."
    )

    # Re-enter the next deal — start_round → reset_round_fields must NOT
    # touch litige_points either.
    state = start_round(state, random.Random(31))
    assert state.phase == Phase.BIDDING
    assert state.litige_points == 92, (
        "reset_round_fields zeroed litige_points; the field is contracted to "
        "carry across rounds (including all-pass redeals)."
    )


def test_litige_pool_survives_two_consecutive_all_pass_redeals() -> None:
    """Two consecutive all-pass redeals still preserve the pool. Pins
    against a future regression that resets `litige_points` on the second
    pass through `start_round`."""
    state = new_game()
    state = start_round(state, random.Random(37))
    state = replace(state, litige_points=162)

    for _ in range(8):
        state = process_bid(state, None)
    state = start_round(state, random.Random(41))
    for _ in range(8):
        state = process_bid(state, None)
    state = start_round(state, random.Random(43))

    assert state.litige_points == 162


def test_litige_pool_consumed_after_normal_round_following_redeals() -> None:
    """4.8.2 (T1): end-to-end pin. Round 1 is litige (pool: 80). Round 2 +
    round 3 both all-pass (pool persists at 80). Round 4 is a normal
    contract that the taker wins — the consume path runs and the litige
    pool resets to 0.
    """
    from belote.scoring import ScoringBreakdown, apply_round_score

    state = new_game()
    state = start_round(state, random.Random(37))
    # Round 1: simulate a litige outcome (don't actually play 32 cards —
    # just stamp a litige breakdown). apply_round_score then carries the
    # awarded points into the run-level pool.
    breakdown = ScoringBreakdown(
        taker_team=0,
        table_taker_pts=80,
        table_defender_pts=80,
        credit_taker_pts=0,
        credit_defender_pts=80,
        last_trick_team=0,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=0,
        defender_total=80,
        is_capot=False,
        is_failed=False,
        is_litige=True,
        litige_points_awarded=80,
    )
    state = apply_round_score(state, breakdown)
    assert state.litige_points == 80, "Round 1 litige did not seed the pool"

    # Rounds 2 & 3: all-pass. Pool must survive both.
    for _ in range(8):
        state = process_bid(state, None)
    state = start_round(state, random.Random(41))
    assert state.litige_points == 80
    for _ in range(8):
        state = process_bid(state, None)
    state = start_round(state, random.Random(43))
    assert state.litige_points == 80, "Pool dropped across two consecutive all-pass redeals"

    # Round 4: normal contract, taker wins. The breakdown's taker_total
    # would include the litige_points (added in `_score_normal_outcome`),
    # and `apply_round_score` then RESETS the pool to 0.
    success = ScoringBreakdown(
        taker_team=0,
        table_taker_pts=100,
        table_defender_pts=62,
        credit_taker_pts=100,
        credit_defender_pts=62,
        last_trick_team=0,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=180,  # 100 card pts + 80 carried litige
        defender_total=62,
        is_capot=False,
        is_failed=False,
        is_litige=False,
    )
    state = apply_round_score(state, success)
    assert state.litige_points == 0, (
        f"litige pool not consumed by normal-round success: "
        f"litige_points={state.litige_points}"
    )
