"""Scoring-total pins (4.9.6).

Freezes the canonical Belote point totals the audit verified by hand. These are
the numbers the whole scoring engine is built on; pinning them here makes any
future change to a point table or bonus constant an explicit, reviewed decision
rather than a silent balance shift.
"""

from __future__ import annotations

from belote.config import GLOBAL_CONFIG
from belote.deck import Rank, Suit, card_points, make_deck


def _suit_trump_sum(trump: Suit | None) -> int:
    return sum(card_points(c, trump) for c in make_deck())


def test_card_point_totals_per_contract() -> None:
    # Normal contract: 30 per plain suit (×3) + 62 trump = 152.
    assert _suit_trump_sum(Suit.SPADES) == 152
    # Sans Atout: every suit plain → 120.
    assert _suit_trump_sum(None) == 120
    # Tout Atout: every suit trump → 248.
    assert _suit_trump_sum(Suit.TOUT_ATOUT) == 248


def test_point_totals_match_declared_constants() -> None:
    assert GLOBAL_CONFIG.TOTAL_POINTS == 152
    assert GLOBAL_CONFIG.TOTAL_POINTS_SANS_ATOUT == 120
    assert GLOBAL_CONFIG.TOTAL_POINTS_TOUT_ATOUT == 248
    # Cross-check the live tables against the declared constants.
    assert _suit_trump_sum(Suit.SPADES) == GLOBAL_CONFIG.TOTAL_POINTS
    assert _suit_trump_sum(None) == GLOBAL_CONFIG.TOTAL_POINTS_SANS_ATOUT
    assert _suit_trump_sum(Suit.TOUT_ATOUT) == GLOBAL_CONFIG.TOTAL_POINTS_TOUT_ATOUT


def test_belote_rebelote_is_twenty_total() -> None:
    # 20 points TOTAL across the pair, not 20 each (4.9.5 fix).
    assert GLOBAL_CONFIG.BELOTE_POINTS == 20
    assert GLOBAL_CONFIG.REBELOTE_POINTS == 20


def test_capot_bases_per_contract() -> None:
    # Base = contract total + 100 bonus (and includes the +10 dix de der).
    assert GLOBAL_CONFIG.CAPOT_BASE == 252  # 152 + 100
    assert GLOBAL_CONFIG.CAPOT_BASE_SANS_ATOUT == 220  # 120 + 100
    assert GLOBAL_CONFIG.CAPOT_BASE_TOUT_ATOUT == 348  # 248 + 100


def test_dix_de_der_bonus() -> None:
    assert GLOBAL_CONFIG.LAST_TRICK_BONUS == 10


def test_trump_jack_and_nine_are_top_trumps() -> None:
    # Trump ranking J(20) > 9(14) > A(11) > 10(10) > K(4) > Q(3) > 8/7(0).
    j = card_points(next(c for c in make_deck()
                         if c.suit == Suit.SPADES and c.rank == Rank.JACK), Suit.SPADES)
    nine = card_points(next(c for c in make_deck()
                            if c.suit == Suit.SPADES and c.rank == Rank.NINE), Suit.SPADES)
    assert j == 20
    assert nine == 14
