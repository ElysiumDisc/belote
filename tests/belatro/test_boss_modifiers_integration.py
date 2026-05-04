"""Boss modifier integration tests."""

from __future__ import annotations

from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard
from belote.scoring import score_round


def test_boss_no_belote():
    """1. Boss: No Belote - Verify belote points are suppressed."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(no_belote=True),
        belote_holders={Suit.HEARTS: Seat.SOUTH},
        belote_tracker=(True, True)
    )
    breakdown = score_round(state)
    assert not any("Belote" in m for m in breakdown.messages)
    assert breakdown.table_taker_pts == 0


def _trick_won_by_south(card: Card) -> tuple[TrickCard, ...]:
    """Build a 4-card trick where South leads `card` and partner/defenders dump filler.

    Used by boss-modifier tests that need a valid trick where South wins.
    """
    # South leads the card under test (trump=HEARTS in callers, so a SPADES lead
    # gets followed by SPADES from N/E/W with lower ranks; South wins).
    return (
        TrickCard(Seat.SOUTH, card),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
    )


def test_boss_kings_zero():
    """2. Boss: Kings Zero - Verify Kings score 0 points."""
    # South captures four Kings of Spades across four tricks (one per suit-rank
    # combo would normally be impossible; we just need the kings_zero rule to
    # zero out card points for tricks containing kings).
    king_tricks = tuple(
        _trick_won_by_south(Card(Suit.SPADES, Rank.KING)) for _ in range(4)
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(kings_zero=True),
        completed_tricks=king_tricks,
    )
    breakdown = score_round(state)
    # Without boss: 4 kings = 4×4 = 16 + filler. With kings_zero: kings drop to 0.
    assert breakdown.table_taker_pts == 0


def test_boss_tens_zero():
    """3. Boss: Tens Zero - Verify Tens score 0 points."""
    ten_tricks = tuple(
        _trick_won_by_south(Card(Suit.SPADES, Rank.TEN)) for _ in range(4)
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(tens_zero=True),
        completed_tricks=ten_tricks,
    )
    breakdown = score_round(state)
    # Without boss: 4 tens = 4×10 = 40 + filler. With tens_zero: tens drop to 0.
    assert breakdown.table_taker_pts == 0


def test_boss_queen_spades_penalty():
    """6. Boss: Queen of Spades Penalty - Verify -25 points for QS."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(queen_spades_penalty=True),
        completed_tricks=tuple(
            [(TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.QUEEN)),
              TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.SEVEN)),
              TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.EIGHT)),
              TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.NINE)))] +
            [(TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.ACE)),
              TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.TEN)),
              TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.KING)),
              TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.QUEEN)))] * 7
        ),
        last_trick_winner=Seat.EAST
    )
    breakdown = score_round(state)
    assert any("Reine Noire" in m for m in breakdown.messages)
    # Taker Card points: QS (0) + 7 other tricks (0 because they lost them) = 0
    # Penalty -25. Result should be -25 or chute.
    assert breakdown.table_taker_pts < 0


def test_boss_invert_scoring():
    """9. Boss: Invert Scoring (La Malédiction) — winning more tricks zeroes you."""
    # Build 5 tricks NS wins, 3 tricks EW wins. Under invert_scoring,
    # NS won more tricks so taker_total should be zeroed out.
    ns_win = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),  # trump
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    ew_win = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),  # trump, beats NS
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.QUEEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.TEN)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(invert_scoring=True),
        completed_tricks=tuple([ns_win] * 5 + [ew_win] * 3),
        last_trick_winner=Seat.EAST,
    )
    breakdown = score_round(state)
    # NS won 5 tricks > EW's 3 → invert_scoring zeroes NS total.
    assert breakdown.taker_total == 0
    assert any("Malédiction" in m for m in breakdown.messages)
