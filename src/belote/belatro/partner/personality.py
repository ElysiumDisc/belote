from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import Counter

from belote.game import SANS_ATOUT_BID, BidValue, GameState, Seat, Suit


class PartnerPersonality(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def should_bid(self, state: GameState) -> bool:
        """Return True if partner should open the bidding."""
        ...

    @abstractmethod
    def bid_value(self, state: GameState) -> BidValue:
        """Return the contract the partner bids: a Suit, `Suit.TOUT_ATOUT`,
        the `SANS_ATOUT_BID` sentinel, or None.

        The round driver gates TA/SA returns on `partner.trust.duo_contracts_available`
        — personalities can return them freely; trust enforces availability.
        """
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

    def bid_value(self, state: GameState) -> BidValue:
        from belote.deck import Rank

        hand = state.hand_of(Seat.NORTH)
        # Round-2-only: prefer Tout Atout when the hand is Jack-heavy across
        # multiple suits (every suit acts as trump under TA, so distributed
        # Jacks are the strongest TA signal). Trust gating happens in
        # round_driver — we just propose; engine accepts or rejects.
        if state.bidding_round == 2:
            jack_suits = {c.suit for c in hand if c.rank == Rank.JACK and c.suit.is_card_suit}
            jack_count = sum(1 for c in hand if c.rank == Rank.JACK)
            if jack_count >= 3 and len(jack_suits) >= 3:
                return Suit.TOUT_ATOUT

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

    def bid_value(self, state: GameState) -> BidValue:
        up = state.up_card
        return up.suit if up else None


class LeFlambeur(PartnerPersonality):
    id = "le_flambeur"
    name = "Le Flambeur"
    description = "Bids aggressively. Will randomly Coinche."

    def should_bid(self, state: GameState) -> bool:
        from belote.deck import Rank

        hand = state.hand_of(Seat.NORTH)
        if not hand:
            return False
        # Aggressive but hand-aware: bid whenever the strongest suit has any
        # honor (J/9/A) — that's roughly twice as often as Le Courageux's
        # "2+ honors anywhere" and roughly half as often as the previous flat
        # 40% coin-flip, so it lives up to "aggressive" without being random.
        honors = {Rank.JACK, Rank.NINE, Rank.ACE}
        per_suit_honors = Counter(
            c.suit for c in hand if c.rank in honors and c.suit.is_card_suit
        )
        if not per_suit_honors:
            return False
        return per_suit_honors.most_common(1)[0][1] >= 1

    def bid_value(self, state: GameState) -> BidValue:
        hand = state.hand_of(Seat.NORTH)
        if not hand:
            return None
        # Pick the longest suit; tiebreak on most honors. Beats picking a
        # random suit, which the audit flagged.
        from belote.deck import Rank

        honors = {Rank.JACK, Rank.NINE, Rank.ACE}
        length = Counter(c.suit for c in hand if c.suit.is_card_suit)
        if not length:
            return None
        honor_count = Counter(
            c.suit for c in hand if c.rank in honors and c.suit.is_card_suit
        )
        return max(length, key=lambda s: (length[s], honor_count[s]))

    def should_coinche(self, state: GameState) -> bool:
        return random.random() < 0.2


class LeSacrifie(PartnerPersonality):
    id = "le_sacrifie"
    name = "Le Sacrifié"
    description = "Plays to maximize your trick count; ignores own hand value."

    def should_bid(self, state: GameState) -> bool:
        return False

    def bid_value(self, state: GameState) -> BidValue:
        return None


class LeFantome(PartnerPersonality):
    id = "le_fantome"
    name = "Le Fantôme"
    description = "Makes no signals; invisible playstyle. Every trick they win gives you +$1."

    def should_bid(self, state: GameState) -> bool:
        return False

    def bid_value(self, state: GameState) -> BidValue:
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

    def bid_value(self, state: GameState) -> BidValue:
        from belote.deck import Rank

        hand = state.hand_of(Seat.NORTH)
        # Round-2-only: prefer Sans Atout on a flat Ace/10-heavy hand. Under SA
        # the Ace is master in every suit and long suits are a liability.
        if state.bidding_round == 2:
            ace_ten = sum(1 for c in hand if c.rank in (Rank.ACE, Rank.TEN))
            lengths = Counter(c.suit for c in hand if c.suit.is_card_suit)
            if ace_ten >= 3 and (max(lengths.values(), default=0) <= 3):
                return SANS_ATOUT_BID

        c = Counter(card.suit for card in hand)
        suits = sorted(c, key=lambda s: c[s], reverse=True)
        return suits[0] if suits else None
