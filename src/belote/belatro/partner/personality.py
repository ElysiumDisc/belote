from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import Counter

from belote.game import GameState, Seat, Suit


class PartnerPersonality(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def should_bid(self, state: GameState) -> bool:
        """Return True if partner should open the bidding."""
        ...

    @abstractmethod
    def bid_value(self, state: GameState) -> Suit | None:
        """Return the suit the partner bids when they do open."""
        ...

    def should_coinche(self, state: GameState) -> bool:
        """Return True if partner should Coinche."""
        return False


class LeCourageux(PartnerPersonality):
    id = "le_courageux"
    name = "Le Courageux"
    description = "Bids on 2+ honors. Sometimes overbids."

    def should_bid(self, state: GameState) -> bool:
        from belote.deck import Rank

        hand = state.hand_of(Seat.NORTH)
        honors = sum(1 for c in hand if c.rank in (Rank.ACE, Rank.KING, Rank.JACK))
        return honors >= 2

    def bid_value(self, state: GameState) -> Suit | None:
        hand = state.hand_of(Seat.NORTH)
        c = Counter(card.suit for card in hand)
        suits = sorted(c, key=lambda s: c[s], reverse=True)
        return suits[0] if suits else None


class LEconome(PartnerPersonality):
    id = "l_econome"
    name = "L'Économe"
    description = "Passes unless holding the trump Jack."

    def should_bid(self, state: GameState) -> bool:
        hand = state.hand_of(Seat.NORTH)
        from belote.deck import Rank

        up = state.up_card
        if up is None:
            return False
        return any(c.suit == up.suit and c.rank == Rank.JACK for c in hand)

    def bid_value(self, state: GameState) -> Suit | None:
        up = state.up_card
        return up.suit if up else None


class LeFlambeur(PartnerPersonality):
    id = "le_flambeur"
    name = "Le Flambeur"
    description = "Bids aggressively. Will randomly Coinche."

    def should_bid(self, state: GameState) -> bool:
        hand = state.hand_of(Seat.NORTH)
        return len(hand) > 0 and random.random() < 0.4

    def bid_value(self, state: GameState) -> Suit | None:
        hand = state.hand_of(Seat.NORTH)
        if not hand:
            return None
        return random.choice(list(Suit))

    def should_coinche(self, state: GameState) -> bool:
        return random.random() < 0.2


class LeSacrifie(PartnerPersonality):
    id = "le_sacrifie"
    name = "Le Sacrifié"
    description = "Plays to maximize your trick count; ignores own hand value."

    def should_bid(self, state: GameState) -> bool:
        return False

    def bid_value(self, state: GameState) -> Suit | None:
        return None


class LeFantome(PartnerPersonality):
    id = "le_fantome"
    name = "Le Fantôme"
    description = "Makes no signals; invisible playstyle. Every trick they win gives you +$1."

    def should_bid(self, state: GameState) -> bool:
        return False

    def bid_value(self, state: GameState) -> Suit | None:
        return None


class LeStratege(PartnerPersonality):
    id = "le_stratege"
    name = "Le Stratège"
    description = "Sends legal card-lead signals about their hand."

    def should_bid(self, state: GameState) -> bool:
        hand = state.hand_of(Seat.NORTH)
        from belote.deck import Rank

        high_value = sum(1 for c in hand if c.rank in (Rank.ACE, Rank.JACK, Rank.NINE))
        return high_value >= 3

    def bid_value(self, state: GameState) -> Suit | None:
        hand = state.hand_of(Seat.NORTH)
        c = Counter(card.suit for card in hand)
        suits = sorted(c, key=lambda s: c[s], reverse=True)
        return suits[0] if suits else None
