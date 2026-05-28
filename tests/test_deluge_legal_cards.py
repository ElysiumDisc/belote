"""Legal-card correctness under La Déluge (`seven_eight_trump`).

La Déluge makes every 7 and 8 rank as trump, regardless of suit. Following a
trump lead therefore means following with ANY trump the player holds — including
off-suit 7s/8s — not just cards whose suit matches the lead suit.

Regression for the crash where a player void of the trump *suit* but holding
only off-suit 7/8 cards (which ARE trumps) received an empty legal set, which
in turn tripped `AIPlayer.decide_card`'s empty-legal assertion.
"""

from __future__ import annotations

from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard, legal_cards


def _state(hand: tuple[Card, ...], lead: Card) -> GameState:
    return GameState(
        hands=(hand, (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,
        contract="hearts",
        taker=Seat.WEST,
        current_trick=(TrickCard(Seat.WEST, lead),),
        boss_modifiers=BossModifiers(seven_eight_trump=True),
    )


def test_off_suit_seven_eight_are_legal_when_trump_led() -> None:
    """Void in the trump suit but holding off-suit 7/8 (which are trumps under
    La Déluge): those 7/8 must be legal, not an empty set."""
    hand = (Card(Suit.SPADES, Rank.SEVEN), Card(Suit.DIAMONDS, Rank.EIGHT))
    legal = legal_cards(_state(hand, Card(Suit.HEARTS, Rank.JACK)), Seat.SOUTH)
    assert set(legal) == set(hand), (
        "off-suit 7/8 are trumps under La Déluge and must be legal on a trump lead"
    )


def test_trump_led_excludes_non_trump_when_trumps_held() -> None:
    """Holding trumps (trump-suit 7H and off-suit 7S) plus a non-trump (KC):
    must follow with trumps; the non-trump is illegal."""
    hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.KING),
    )
    legal = legal_cards(_state(hand, Card(Suit.HEARTS, Rank.EIGHT)), Seat.SOUTH)
    assert Card(Suit.CLUBS, Rank.KING) not in legal
    assert Card(Suit.HEARTS, Rank.SEVEN) in legal
    assert Card(Suit.SPADES, Rank.SEVEN) in legal


def test_trump_led_overtrump_obligation_with_off_suit_trump() -> None:
    """Trump-rank order is J>9>A>10>K>Q>8>7. WEST leads 7H (lowest trump).
    SOUTH holds 8S (a trump that beats 7) and KC (non-trump): must overtrump
    with the 8S, KC stays illegal."""
    hand = (Card(Suit.SPADES, Rank.EIGHT), Card(Suit.CLUBS, Rank.KING))
    legal = legal_cards(_state(hand, Card(Suit.HEARTS, Rank.SEVEN)), Seat.SOUTH)
    assert set(legal) == {Card(Suit.SPADES, Rank.EIGHT)}


def test_no_trumps_at_all_allows_free_play_on_trump_lead() -> None:
    """Genuinely void of every trump (no trump suit, no 7/8): may play anything."""
    hand = (Card(Suit.CLUBS, Rank.KING), Card(Suit.DIAMONDS, Rank.QUEEN))
    legal = legal_cards(_state(hand, Card(Suit.HEARTS, Rank.JACK)), Seat.SOUTH)
    assert set(legal) == set(hand)
