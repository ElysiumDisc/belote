from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Suit(Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"

    @property
    def symbol(self) -> str:
        return self.value

    @property
    def is_red(self) -> bool:
        return self in (Suit.HEARTS, Suit.DIAMONDS)


class Rank(Enum):
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"


@dataclass(frozen=True, slots=True)
class Card:
    suit: Suit
    rank: Rank

    def __repr__(self) -> str:
        return f"{self.rank.value}{self.suit.symbol}"


def make_deck() -> tuple[Card, ...]:
    """Return 32 cards in deterministic order: suits in S/H/D/C, ranks 7→A."""
    suits = list(Suit)
    ranks = list(Rank)
    return tuple(Card(s, r) for s in suits for r in ranks)


def shuffle(deck: tuple[Card, ...], rng: random.Random) -> tuple[Card, ...]:
    """Shuffle deck in place (well, returns new shuffled tuple)."""
    lst = list(deck)
    rng.shuffle(lst)
    return tuple(lst)


def deal(deck: tuple[Card, ...]) -> tuple[tuple[tuple[Card, ...], ...], Card, tuple[Card, ...]]:
    """Deal for Belote:
    1. Initial deal: 5 cards each (3 then 2).
    2. Up-card: the 21st card.
    3. Remaining cards: 3 cards each (totaling 8).
    Returns (initial_hands, up_card, remaining_cards).
    """
    initial: list[list[Card]] = [[], [], [], []]

    idx = 0
    # First 3
    for _ in range(3):
        for h in initial:
            h.append(deck[idx])
            idx += 1
    # Next 2
    for _ in range(2):
        for h in initial:
            h.append(deck[idx])
            idx += 1

    # Up-card
    up_card = deck[idx]
    idx += 1

    # Remaining 11 cards
    # We'll just return them as a flat tuple and distribute in game.py
    remaining_pool = deck[idx:]
    return (
        tuple(tuple(h) for h in initial),
        up_card,
        remaining_pool
    )


# Trump ranking: J=7, 9=6, A=5, 10=4, K=3, Q=2, 8=1, 7=0 (higher = stronger)
_TRUMP_ORDER: dict[Rank, int] = {
    Rank.SEVEN: 0,
    Rank.EIGHT: 1,
    Rank.QUEEN: 2,
    Rank.KING: 3,
    Rank.TEN: 4,
    Rank.ACE: 5,
    Rank.NINE: 6,
    Rank.JACK: 7,
}

# Non-trump ranking: A=7, 10=6, K=5, Q=4, J=3, 9=2, 8=1, 7=0
_NONTRUMP_ORDER: dict[Rank, int] = {
    Rank.SEVEN: 0,
    Rank.EIGHT: 1,
    Rank.NINE: 2,
    Rank.JACK: 3,
    Rank.QUEEN: 4,
    Rank.KING: 5,
    Rank.TEN: 6,
    Rank.ACE: 7,
}


def trick_rank(card: Card, trump: Suit) -> int:
    """Higher value = stronger card. Returns 0-15 (trump cards get 8-15)."""
    if card.suit == trump:
        return 8 + _TRUMP_ORDER[card.rank]
    return _NONTRUMP_ORDER[card.rank]


def card_points(card: Card, trump: Suit) -> int:
    """Point value of a card. Sum over all 32 cards = 152."""
    if card.suit == trump:
        match card.rank:
            case Rank.JACK:
                return 20
            case Rank.NINE:
                return 14
            case Rank.ACE:
                return 11
            case Rank.TEN:
                return 10
            case Rank.KING:
                return 4
            case Rank.QUEEN:
                return 3
            case Rank.EIGHT | Rank.SEVEN:
                return 0
            case _:
                return 0
    else:
        match card.rank:
            case Rank.JACK:
                return 2
            case Rank.NINE | Rank.EIGHT | Rank.SEVEN:
                return 0
            case Rank.ACE:
                return 11
            case Rank.TEN:
                return 10
            case Rank.KING:
                return 4
            case Rank.QUEEN:
                return 3
            case _:
                return 0
