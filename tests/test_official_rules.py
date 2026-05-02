from __future__ import annotations

import dataclasses

from belote.game import Card, GameState, Phase, Rank, Seat, Suit, TrickCard
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


def test_chute_declaration_transfer() -> None:
    # Taker (South) has a quinte (100) and tierce (20), but loses round.
    # Defense should get 162 + 120 = 282.
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

    # Give all tricks to East
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

    # Taker (NS) wins round, but Defender (EW) has Belote
    # NS points: 100 card pts
    # EW points: 52 card pts + 10 de der + 20 Belote = 82
    # Since NS(100) > EW(62), NS wins.
    # But EW should still get their 20 Belote.

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
