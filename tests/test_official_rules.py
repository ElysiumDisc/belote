from __future__ import annotations

import dataclasses
import random

import pytest

from belote.game import (
    SANS_ATOUT_BID,
    Card,
    GameState,
    IllegalMoveError,
    Phase,
    Rank,
    Seat,
    Suit,
    TrickCard,
    new_game,
    place_bid,
    start_round,
)
from belote.scoring import score_round


def test_litige_detection() -> None:
    # Setup a state where Taker (NS) and Defense (EW) have exactly same points (81 each)
    # NS has 81 card points. EW has 71 card points + 10 de der = 81.

    # NS Tricks (Total 81)
    ns_tricks = [
        # Trick 1: NS wins with Trump J (20) + 9(14) + 7(0) + 8(0) = 34
        (
            TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),
            TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
            TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),
            TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.EIGHT)),
        ),
        # Trick 2: NS wins with Clubs A(11) + 10(10) + K(4) + Q(3) = 28
        (
            TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.ACE)),
            TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.QUEEN)),
        ),
        # Trick 3: NS wins with Diamonds A(11) + K(4) + Spades K(4) + 7(0) = 19
        (
            TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.ACE)),
            TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.KING)),
            TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
        ),
    ]
    # Total NS: 34 + 28 + 19 = 81.

    # EW Tricks (Total 71)
    ew_tricks = [
        # Trick 4: EW wins with Hearts A(11) + 10(10) + K(4) + Q(3) = 28
        (
            TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),
            TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.QUEEN)),
        ),
        # Trick 5: EW wins with Spades A(11) + 10(10) + Q(3) + J(2) = 26
        (
            TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.ACE)),
            TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.QUEEN)),
            TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.JACK)),
        ),
        # Trick 6: EW wins with Diamonds 10(10) + Q(3) + J(2) + Clubs J(2) = 17
        (
            TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.TEN)),
            TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.QUEEN)),
            TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.JACK)),
            TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.JACK)),
        ),
    ]
    # Total EW: 28 + 26 + 17 = 71.

    state = GameState(
        hands=tuple([()] * 4),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        completed_tricks=tuple(ns_tricks + ew_tricks),
        last_trick_winner=Seat.EAST,  # Defense gets 10 de der -> 71 + 10 = 81
        team_scores=(0, 0),
        phase=Phase.SCORING,
    )

    breakdown = score_round(state)
    assert breakdown.is_litige is True
    assert breakdown.taker_total == 0
    assert breakdown.defender_total == 81
    assert breakdown.litige_points_awarded == 81


def test_capot_against_taker_transfers_declarations() -> None:
    # Taker (South) has a quinte (100) and tierce (20) but the defense (EW)
    # captures all 8 tricks → capot against the taker. Per official rules,
    # the taker's declarations transfer to the defense.
    # Defense should get CAPOT_BASE + transferred decls = 252 + 120 = 372.
    from belote.config import GLOBAL_CONFIG

    south_hand = (
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.HEARTS, Rank.QUEEN),  # tierce
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.SPADES, Rank.KING),
        Card(Suit.SPADES, Rank.QUEEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.SPADES, Rank.TEN),  # quinte
    )

    tricks = []
    for i in range(8):
        tricks.append(
            (
                TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.ACE)),
                TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.SEVEN if i == 0 else Rank.EIGHT)),
                TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.SEVEN)),
                TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.EIGHT)),
            )
        )

    breakdown = score_round(
        GameState(
            hands=tuple([()] * 4),
            initial_hands=(south_hand, (), (), ()),
            trump=Suit.CLUBS,
            taker=Seat.SOUTH,
            completed_tricks=tuple(tricks),
            last_trick_winner=Seat.EAST,
            phase=Phase.SCORING,
        )
    )

    assert breakdown.is_capot is True
    assert breakdown.is_failed is True
    assert breakdown.taker_total == 0
    # 252 (capot base) + 120 (NS quinte+tierce transferred) = 372
    assert breakdown.defender_total == GLOBAL_CONFIG.CAPOT_BASE + 120


def test_defender_belote_kept_on_taker_success() -> None:
    # Taker (NS) wins the round, but Defender (EW) holds belote (K-Q of trump).
    # EW should still receive their 20 belote points even though they lost the round.
    #
    # NS points: 101 card pts
    # EW points: 51 card pts + 10 de der + 20 Belote = 81
    # NS(101) > EW(51) so NS wins; EW keeps belote.

    # Simple tricks to get 100 for NS
    ns_tricks = [
        (
            TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),
            TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.SEVEN)),
            TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
            TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.NINE)),
        ),  # J=20, 9=14 -> 34
        (
            TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.ACE)),
            TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.QUEEN)),
        ),  # 28
        (
            TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.ACE)),
            TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.QUEEN)),
        ),  # 28
        (
            TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
            TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.SEVEN)),
            TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
            TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.NINE)),
        ),  # 11
    ]
    # Total NS: 34 + 28 + 28 + 11 = 101.

    # Give EW the rest
    ew_tricks = [
        (
            TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.TEN)),
            TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.QUEEN)),
            TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.JACK)),
            TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.KING)),
        ),  # 10+3+2+4 = 19
        (
            TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.JACK)),
            TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.NINE)),
            TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.EIGHT)),
            TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.SEVEN)),
        ),  # 2
        (
            TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.JACK)),
            TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.NINE)),
            TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.EIGHT)),
            TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.SEVEN)),
        ),  # 2
        (
            TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),
            TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.KING)),
            TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.QUEEN)),
        ),  # 11+10+4+3 = 28
    ]
    # Total EW: 19 + 2 + 2 + 28 = 51.
    # Total: 101 + 51 = 152.

    # Give East the Belote cards in initial hand
    east_hand = (Card(Suit.HEARTS, Rank.KING), Card(Suit.HEARTS, Rank.QUEEN))

    state = GameState(
        hands=tuple([()] * 4),
        initial_hands=((), east_hand, (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        completed_tricks=tuple(ns_tricks + ew_tricks),
        last_trick_winner=Seat.EAST,  # EW gets 10 de der
        belote_holders={Suit.HEARTS: Seat.EAST},
        belote_tracker=(True, False),  # Belote announced
        phase=Phase.SCORING,
    )

    breakdown = score_round(state)
    assert breakdown.is_failed is False
    assert breakdown.taker_total == 101  # NS card pts
    assert breakdown.defender_total == 51 + 10 + 20  # EW card pts + 10 de der + Belote = 81


def test_ew_taker_capot() -> None:
    # EW takes and gets Capot
    tricks = []
    for _ in range(8):
        tricks.append(
            (
                TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.JACK)),
                TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),
                TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.EIGHT)),
                TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.NINE)),
            )
        )

    state = GameState(
        hands=tuple([()] * 4),
        trump=Suit.HEARTS,
        taker=Seat.EAST,
        completed_tricks=tuple(tricks),
        last_trick_winner=Seat.EAST,
        phase=Phase.SCORING,
    )

    breakdown = score_round(state)
    assert breakdown.is_capot is True
    assert breakdown.taker_team == 1  # EW
    assert breakdown.taker_total == 252
    assert breakdown.defender_total == 0


def test_sequence_trump_bonus() -> None:
    # Sequence of same length, higher top wins.
    # If same top, trump sequence wins.
    ns_hand = (
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.CLUBS, Rank.KING),
        Card(Suit.CLUBS, Rank.QUEEN),
    )  # tierce to Ace
    ew_hand = (
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.HEARTS, Rank.QUEEN),
    )  # tierce to Ace

    # If Hearts is trump, EW should win the sequences
    state = GameState(
        hands=tuple([()] * 4),
        initial_hands=(ns_hand, ew_hand, (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
    )

    from belote.scoring import _detect_all_declarations, resolve_declarations

    decls = _detect_all_declarations(state, Suit.HEARTS)
    resolved = resolve_declarations(decls, Suit.HEARTS)

    assert resolved.scoring_team == 1  # EW wins because of trump tierce

    # If Diamonds is trump (none of the sequences are trump), they should cancel out (None)
    state = dataclasses.replace(state, trump=Suit.DIAMONDS)
    decls = _detect_all_declarations(state, Suit.DIAMONDS)
    resolved = resolve_declarations(decls, Suit.DIAMONDS)
    assert resolved.scoring_team is None  # cancel


# ── B4 regression: Tout Atout legal_cards ──────────────────────────────────


def _ta_state(south_hand, current_trick, leader=Seat.NORTH):
    """Build a minimal PLAYING-phase TA state with South to play."""
    hands = [(), (), (), ()]
    hands[Seat.SOUTH.value] = south_hand
    return GameState(
        hands=tuple(hands),
        trump=Suit.TOUT_ATOUT,
        contract="tout_atout",
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
        leader=leader,
        turn=Seat.SOUTH,
        current_trick=current_trick,
    )


def test_tout_atout_must_overtake_within_lead_suit() -> None:
    """Under Tout Atout, holding ♥7 and ♥J after partner leads ♥7: must rise
    with the Jack (the only riser within ♥) — pre-fix this fell into the
    non-trump-led branch and allowed the 7 too."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.SPADES, Rank.ACE),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _ta_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert legal == (Card(Suit.HEARTS, Rank.JACK),)


def test_tout_atout_must_follow_suit() -> None:
    """Under Tout Atout, holding hearts and spades when hearts is led: must
    follow hearts only — off-suit play is illegal."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.HEARTS, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.SPADES, Rank.ACE),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _ta_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert set(legal) == {Card(Suit.HEARTS, Rank.QUEEN), Card(Suit.HEARTS, Rank.NINE)}


def test_tout_atout_void_can_discard_anything() -> None:
    """Under Tout Atout, void in lead suit → free discard. No 'must trump'
    rule because off-suit cards never beat the lead suit."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.JACK),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _ta_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert set(legal) == set(south_hand)


# ── F3/F4 regression: Sans Atout engine + scoring ─────────────────────────


def _sa_state(south_hand, current_trick, leader=Seat.NORTH):
    """Build a minimal PLAYING-phase Sans Atout state with South to play."""
    hands = [(), (), (), ()]
    hands[Seat.SOUTH.value] = south_hand
    return GameState(
        hands=tuple(hands),
        trump=None,
        contract="sans_atout",
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
        leader=leader,
        turn=Seat.SOUTH,
        current_trick=current_trick,
    )


def test_sans_atout_must_follow_lead_suit() -> None:
    """Under Sans Atout (trump=None, contract='sans_atout') with hearts and
    spades in hand: must follow hearts only when hearts is led."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.HEARTS, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.SPADES, Rank.ACE),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _sa_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert set(legal) == {Card(Suit.HEARTS, Rank.QUEEN), Card(Suit.HEARTS, Rank.NINE)}


def test_sans_atout_void_can_discard_anything() -> None:
    """Under Sans Atout, void in lead suit → free discard. No 'must trump'
    rule; off-suit cards never beat the lead-suit hand anyway."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.JACK),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _sa_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert set(legal) == set(south_hand)


def test_sans_atout_no_overtake_required() -> None:
    """Under Sans Atout, when you can follow suit, you can play any of your
    lead-suit cards — no must-rise rule like under Tout Atout."""
    from belote.game import legal_cards

    south_hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.JACK),
    )
    trick = (TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),)
    state = _sa_state(south_hand, trick)
    legal = legal_cards(state, Seat.SOUTH)
    assert set(legal) == set(south_hand)  # both legal — no rise rule


def test_sans_atout_trick_winner_lead_suit_only() -> None:
    """Off-suit cards never win under SA; among lead-suit cards, highest
    non-trump rank wins (Ace highest, 7 lowest)."""
    from belote.game import trick_winner_seat

    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),  # not lead-suit master under SA
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.ACE)),  # off-suit, can't win
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.ACE)),  # SA Ace = highest
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.SEVEN)),  # SA lead suit, low
    )
    # Lead is SOUTH's HEARTS.JACK
    winner = trick_winner_seat(trick, None, False, is_sans_atout=True)
    assert winner == Seat.NORTH  # ♥A beats ♥J under non-trump scale


def test_sans_atout_score_round_baseline() -> None:
    """SA round, 8 tricks all to NS, no declarations, no belote → NS scores
    TOTAL_POINTS_SANS_ATOUT (120) + LAST_TRICK_BONUS (10) = 130."""
    # Build: every trick is taken by SOUTH with the lead-suit Ace
    tricks = []
    for suit in (Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS):
        # Two tricks per suit: A+10+K+Q = 28, then J+9+8+7 = 2
        tricks.append((
            TrickCard(Seat.SOUTH, Card(suit, Rank.ACE)),
            TrickCard(Seat.WEST, Card(suit, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(suit, Rank.KING)),
            TrickCard(Seat.EAST, Card(suit, Rank.QUEEN)),
        ))
        tricks.append((
            TrickCard(Seat.SOUTH, Card(suit, Rank.JACK)),
            TrickCard(Seat.WEST, Card(suit, Rank.NINE)),
            TrickCard(Seat.NORTH, Card(suit, Rank.EIGHT)),
            TrickCard(Seat.EAST, Card(suit, Rank.SEVEN)),
        ))
    state = GameState(
        hands=((), (), (), ()),
        trump=None,
        contract="sans_atout",
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=tuple(tricks),
        last_trick_winner=Seat.SOUTH,
    )
    breakdown = score_round(state)
    # NS won every trick. Total non-trump points = 120 + 10 dix de der = 130.
    # 8 tricks × all-NS = capot. Pre-3.0.0 used flat CAPOT_BASE=252 across
    # contracts; corrected to scale with SA total (120 + 100 bonus = 220).
    assert breakdown.is_capot is True
    assert breakdown.taker_total == 220


def test_sans_atout_no_belote_ever() -> None:
    """Even when NS holds K+Q hearts under SA, no belote awarded — there's
    no trump suit, so K+Q is not 'of trump' for any suit."""
    # Single trick state, give NS hearts K+Q in initial_hands but no belote
    initial_hands = (
        (Card(Suit.HEARTS, Rank.KING), Card(Suit.HEARTS, Rank.QUEEN)),
        (), (), (),
    )
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=initial_hands,
        trump=None,
        contract="sans_atout",
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(),
        belote_holders={},  # post-bid: empty for SA
    )
    breakdown = score_round(state)
    assert breakdown.taker_belote == 0
    assert breakdown.defender_belote == 0


def test_tout_atout_no_belote_ever() -> None:
    """Belote is also disabled under Tout Atout (no unique K+Q-of-trump)."""
    initial_hands = (
        (Card(Suit.HEARTS, Rank.KING), Card(Suit.HEARTS, Rank.QUEEN)),
        (), (), (),
    )
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=initial_hands,
        trump=Suit.TOUT_ATOUT,
        contract="tout_atout",
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(),
        belote_holders={},
    )
    breakdown = score_round(state)
    assert breakdown.taker_belote == 0
    assert breakdown.defender_belote == 0


def _start_round_state() -> GameState:
    return start_round(new_game(target=1000), random.Random(7))


def test_place_bid_sans_atout_round1_rejected() -> None:
    """SA can't be bid in round 1 (round 1 is 'take the up-card suit only')."""
    state = _start_round_state()
    assert state.bidding_round == 1
    with pytest.raises(IllegalMoveError):
        place_bid(state, SANS_ATOUT_BID)


def test_place_bid_tout_atout_round1_rejected() -> None:
    """TA can't be bid in round 1."""
    state = _start_round_state()
    assert state.bidding_round == 1
    with pytest.raises(IllegalMoveError):
        place_bid(state, Suit.TOUT_ATOUT)
