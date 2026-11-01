"""Easy AI: shallow bidding heuristics and random legal play."""

from __future__ import annotations

from ..deck import Card, Rank, Suit
from ..game import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
)
from .base import AIBase


class EasyMixin(AIBase):
    def _easy_special(self, hand: tuple[Card, ...], lengths: dict[Suit, int]) -> BidValue:
        """Pick the contract that best fits the hand shape:
        - Tout Atout if Jack-heavy (≥3 Jacks/9s across ≥3 suits) — Jacks are
          the dominant card under TA in every suit.
        - Sans Atout if Ace-heavy (≥3 Aces+10s) with a flat distribution.
        Aces alone don't trigger TA — under TA the Jack reigns, not the Ace.
        """
        ta_strong = {Rank.JACK, Rank.NINE}
        ta_strong_suits = {c.suit for c in hand if c.rank in ta_strong}
        ta_count = sum(1 for c in hand if c.rank in ta_strong)
        if ta_count >= 3 and len(ta_strong_suits) >= 3:
            return Suit.TOUT_ATOUT

        ace_ten_count = sum(1 for c in hand if c.rank in (Rank.ACE, Rank.TEN))
        if ace_ten_count >= 3 and max(lengths.values(), default=0) <= 3:
            return SANS_ATOUT_BID
        return None

    def _easy_bid(self, hand: tuple[Card, ...], exclude: Suit | None = None) -> Suit | None:
        """Bid if hand has >= 2 trump honors (J, 9, A) in any suit."""
        honors = {Rank.JACK, Rank.NINE, Rank.ACE}
        for suit in Suit:
            if suit == exclude or not suit.is_card_suit:
                continue
            count = sum(1 for c in hand if c.suit == suit and c.rank in honors)
            if count >= 2:
                return suit
        return None

    def _easy_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """Uniform random over legal moves."""
        return self._rng.choice(legal)
