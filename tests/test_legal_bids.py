"""`legal_bids` is the single source of truth for which bids are legal."""

from __future__ import annotations

from belote.deck import Card, Rank, Suit
from belote.game import SANS_ATOUT_BID, GameState, Phase, legal_bids


def _bidding_state(round_no: int) -> GameState:
    return GameState(
        hands=((), (), (), ()),
        phase=Phase.BIDDING,
        up_card=Card(Suit.HEARTS, Rank.JACK),
        bidding_round=round_no,
    )


def test_round_one_is_take_or_pass() -> None:
    assert legal_bids(_bidding_state(1)) == [Suit.HEARTS, None]


def test_round_two_excludes_up_suit_and_adds_specials() -> None:
    assert legal_bids(_bidding_state(2)) == [
        Suit.SPADES,
        Suit.DIAMONDS,
        Suit.CLUBS,
        Suit.TOUT_ATOUT,
        SANS_ATOUT_BID,
        None,
    ]
