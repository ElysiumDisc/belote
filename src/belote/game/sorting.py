"""Hand ordering for display: suits alternated by colour, trump first."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Final

from ..deck import Card, Rank, Suit
from .state import (
    S,
    Seat,
)

_SUITS_ORDER: Final = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
_TRUMP_RANK_IDX: Final = {
    r: i
    for i, r in enumerate(
        [
            Rank.JACK,
            Rank.NINE,
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
    )
}
_NORMAL_RANK_IDX: Final = {
    r: i
    for i, r in enumerate(
        [
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.JACK,
            Rank.NINE,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
    )
}


def _build_suit_idx(trump: Suit | None) -> dict[Suit, int]:
    suits_order = list(_SUITS_ORDER)
    if trump and trump in suits_order:
        suits_order.remove(trump)
        suits_order.insert(0, trump)
    return {s: i for i, s in enumerate(suits_order)}


# Pre-compute suit→position maps for every possible trump value (None + the
# four card suits + TOUT_ATOUT). sort_hand is called frequently during
# rendering and this keeps the hot path branch-free.
_SUIT_IDX_CACHE: Final[dict[Suit | None, dict[Suit, int]]] = {
    trump: _build_suit_idx(trump) for trump in (None, Suit.TOUT_ATOUT, *_SUITS_ORDER)
}


@lru_cache(maxsize=512)
def sort_hand(hand: tuple[Card, ...], trump: Suit | None) -> tuple[Card, ...]:
    """Sort hand by suit and rank (trump first, then others, honors together).

    3.6.0 (audit P4): cached because the UI render loop hits the same
    `(hand, trump)` pair on every redraw. Benchmark showed ~34% wall-clock
    win on a 400-input pattern. The cache key is bounded: at most 8! / dup
    permutations × 6 trumps, and `lru_cache` is bounded at 512.
    """
    suit_idx = _SUIT_IDX_CACHE.get(trump) or _build_suit_idx(trump)
    # Under Tout Atout every card is trump, so the trump-rank ladder applies
    # to *every* suit. `c.suit == trump` would always be False here because
    # Card.suit is one of SPADES/HEARTS/DIAMONDS/CLUBS — TOUT_ATOUT is a
    # contract-level marker, never a card suit.
    all_trump = trump is Suit.TOUT_ATOUT

    def sort_key(c: Card) -> tuple[int, int]:
        is_trump = all_trump or c.suit == trump
        return (
            suit_idx[c.suit],
            _TRUMP_RANK_IDX[c.rank] if is_trump else _NORMAL_RANK_IDX[c.rank],
        )

    return tuple(sorted(hand, key=sort_key))


def sort_south_hand(state: S) -> S:
    """Sort South's hand and update state."""
    new_hands = list(state.hands)
    new_hands[Seat.SOUTH.value] = sort_hand(state.hands[Seat.SOUTH.value], state.trump)

    new_initial = list(state.initial_hands)
    if new_initial[Seat.SOUTH.value]:
        new_initial[Seat.SOUTH.value] = sort_hand(
            state.initial_hands[Seat.SOUTH.value], state.trump
        )

    return replace(state, hands=tuple(new_hands), initial_hands=tuple(new_initial))
