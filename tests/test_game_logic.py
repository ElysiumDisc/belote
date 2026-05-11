from __future__ import annotations

import random

from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, new_game, sort_hand, start_round
from belote.scoring import ScoringBreakdown, apply_round_score


def test_apply_round_score() -> None:
    state = GameState(hands=[(), (), (), ()], team_scores=(100, 50), target=1000)
    score = ScoringBreakdown(
        taker_team=0,
        table_taker_pts=80,
        table_defender_pts=72,
        credit_taker_pts=80,
        credit_defender_pts=72,
        last_trick_team=0,
        taker_declarations=20,
        defender_declarations=0,
        taker_belote=20,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=120,
        defender_total=72,
        is_failed=False,
        is_capot=False,
        messages=(),
    )
    new_state = apply_round_score(state, score)
    assert new_state.team_scores == (220, 122)
    assert new_state.dealer == Seat.EAST  # Dealer should rotate
    assert new_state.phase == Phase.DEAL  # Ready for next round


def test_dealer_rotation_full_cycle() -> None:
    state = new_game()
    assert state.dealer == Seat.SOUTH

    rng = random.Random(42)
    # Mocking round end (17 arguments)
    score = ScoringBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, False, False, 0, 0, False, False, ())
    # 1st round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.EAST

    # 2nd round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.NORTH

    # 3rd round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.WEST

    # 4th round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.SOUTH


def test_start_round_integrity() -> None:
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)

    # Check all 32 cards are present
    all_cards = list(state.remaining_cards) + [state.up_card]
    for h in state.hands:
        all_cards.extend(h)

    assert len(all_cards) == 32
    assert len(set(all_cards)) == 32

    # Initial hands should be 5 cards each
    for h in state.hands:
        assert len(h) == 5

    assert state.phase == Phase.BIDDING


def test_sort_hand_uses_trump_ladder_under_tout_atout() -> None:
    """3.3.3 F1: under Tout Atout every card should sort by the trump rank
    ladder (J > 9 > A > 10 > K > Q > 8 > 7), not the non-trump ladder.

    Pre-3.3.3 the predicate `c.suit == trump` was always false because
    Card.suit is never Suit.TOUT_ATOUT (TA is a contract-level marker,
    not a card suit), so all cards fell through to the non-trump ladder
    and the South hand displayed in the wrong order under TA.
    """
    hand = (
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.SPADES, Rank.NINE),
        Card(Suit.SPADES, Rank.ACE),
    )
    sorted_ta = sort_hand(hand, Suit.TOUT_ATOUT)
    ranks = [c.rank for c in sorted_ta]
    assert ranks == [Rank.JACK, Rank.NINE, Rank.ACE, Rank.SEVEN], (
        f"Tout Atout hand must use trump ladder; got {ranks}"
    )

    # Cross-suit sanity: with two suits, suits are still grouped (by the
    # natural _SUITS_ORDER) and within each suit the trump ladder applies.
    mixed = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.SPADES, Rank.SEVEN),
    )
    sorted_mixed = sort_hand(mixed, Suit.TOUT_ATOUT)
    # Spades first (suit_idx[SPADES]=0), then hearts; within each: J before 7.
    assert sorted_mixed == (
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.SEVEN),
    )

    # Regression guard: normal-trump path unchanged. Hearts trump → hearts
    # use trump ladder, spades use non-trump ladder.
    sorted_hearts = sort_hand(mixed, Suit.HEARTS)
    # Hearts comes first (now suit_idx[HEARTS]=0 because trump-shift), and
    # within hearts: J before 7 (trump ladder). Spades after, non-trump
    # ladder so JACK is *lower* than 7 in terms of rank-pts but `sort_hand`
    # uses the rank-index list — JACK_idx=4, SEVEN_idx=7 → J before 7.
    assert sorted_hearts[0] == Card(Suit.HEARTS, Rank.JACK)
    assert sorted_hearts[1] == Card(Suit.HEARTS, Rank.SEVEN)
