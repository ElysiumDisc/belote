"""`AIPlayer`: the public AI, dispatching each decision to its tier."""

from __future__ import annotations

from ..deck import Card, Suit, trick_rank
from ..game import (
    BidValue,
    GameState,
    Seat,
    legal_cards,
    partner,
)
from .base import Difficulty
from .hard import HardMixin
from .medium import MediumMixin


class AIPlayer(HardMixin, MediumMixin):
    def decide_coinche(self, state: GameState) -> bool:
        """4.9.0 / G1: decide whether to coinche (or 4.9.4: surcoinche).

        Dual-purpose, dispatched on ``state.coinche_level``:

        - level 0 (initial coinche): only the defender team responds; if our
          team is the taker we never coinche our own bid.
        - level 1 (surcoinche): only the taker team responds, redoubling
          back at the defenders who just coinched.
        - level 2+ (already surcoinched): nobody redoubles further.

        Only HARD-tier players act. The hand-strength heuristic is symmetric
        — three+ trumps OR holding the trump Jack signals "we expect to
        win this", which is the same intuition whether you're breaking
        the contract (coinche) or redoubling the breaker (surcoinche).
        EASY / MEDIUM never coinche or surcoinche.
        """
        from ..deck import Rank
        from ..game import team_of

        if self.difficulty != Difficulty.HARD:
            return False
        if state.taker is None or state.trump is None:
            return False
        if state.coinche_level == 0:
            if team_of(self.seat) == team_of(state.taker):
                return False
        elif state.coinche_level == 1:
            if team_of(self.seat) != team_of(state.taker):
                return False
        else:
            return False
        hand = state.hand_of(self.seat)
        trump = state.trump
        # TOUT_ATOUT: every suit is trump — fall back to total hand strength.
        if trump == Suit.TOUT_ATOUT:
            jacks = sum(1 for c in hand if c.rank == Rank.JACK)
            return jacks >= 2  # two jacks on a TA hand is a real threat
        trump_count = sum(1 for c in hand if c.suit == trump)
        has_jack = any(c.rank == Rank.JACK and c.suit == trump for c in hand)
        return trump_count >= 3 or has_jack

    def decide_bid(self, state: GameState) -> BidValue:
        """Decide whether to bid and which contract.

        Returns a normal Suit, `Suit.TOUT_ATOUT`, the `SANS_ATOUT_BID` string,
        or None (pass). TA and SA are only considered in round 2; round 1 is
        "take the up-card suit at the standard contract" only.
        """
        self._se = state.variants.seven_eight_trump
        # Boss: La Solitude (Partner forced pass)
        if state.variants.partner_forced_pass and self.seat == partner(Seat.SOUTH):
            return None

        hand = state.hand_of(self.seat)
        forbidden = state.up_card.suit if state.up_card else None

        if state.bidding_round == 1:
            # Round 1: classic-suit bids only, and only the up-card's suit. Get
            # the heuristic's preferred suit; accept iff it matches the up-card.
            suit_bid = self._suit_bid(hand, state)
            if forbidden and suit_bid == forbidden:
                return suit_bid
            return None

        # Round 2: any suit except the up-card's, plus TA and SA.
        special = self._special_bid(hand, state)
        if special is not None:
            return special
        return self._suit_bid(hand, state, exclude=forbidden)

    def _suit_bid(
        self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None
    ) -> Suit | None:
        """Dispatch to the per-difficulty suit-only heuristic."""
        if self.difficulty == Difficulty.EASY:
            return self._easy_bid(hand, exclude=exclude)
        if self.difficulty == Difficulty.MEDIUM:
            return self._medium_bid(hand, state, exclude=exclude)
        return self._hard_bid(hand, state, exclude=exclude)

    def _special_bid(self, hand: tuple[Card, ...], state: GameState) -> BidValue:
        """Round-2 evaluation of Tout Atout vs Sans Atout. Returns one of those
        if the heuristic favors them strongly; None otherwise (so the caller
        falls back to the suit-only path).

        Heuristics (per-tier thresholds chosen to be conservative — these
        contracts aren't picked unless the hand really fits):
        - Easy: spread-honor TA / flat-Aces SA, simple counting.
        - Medium: weighted sum + personality jitter.
        - Hard: card-points-based + Jack/Ace bonuses.
        """
        # The three special-bid heuristics each need a per-suit length count.
        # Compute once and thread through; recomputing inside every branch
        # was a measurable redundancy noted in the May-2026 perf audit.
        lengths = self._suit_lengths(hand)
        if self.difficulty == Difficulty.EASY:
            return self._easy_special(hand, lengths)
        if self.difficulty == Difficulty.MEDIUM:
            return self._medium_special(hand, state, lengths)
        return self._hard_special(hand, state, lengths)

    def decide_card(self, state: GameState) -> Card:
        """Decide which card to play."""
        hand = state.hand_of(self.seat)
        legal = legal_cards(state, self.seat)
        # La Déluge boss makes 7s and 8s of any suit rank as trump (the two
        # LOWEST trumps — 7 at rank 8, 8 at rank 9, both scoring 0 points;
        # see deck.py::trick_rank and ::card_points). Every ranking / point
        # read in this method must thread `_se` through or the AI under-
        # values trump cards that should beat them.
        self._se = state.variants.seven_eight_trump

        # Boss: L'Agent Double (Partner sabotages on 3 random tricks)
        if state.variants.agent_double_active and self.seat == partner(Seat.SOUTH):
            current_trick = len(state.completed_tricks) + 1
            trump = state.trump
            if current_trick in state.variants.sabotage_tricks and trump is not None:
                return min(legal, key=lambda c: trick_rank(c, trump, self._se))

        if not hand:
            # Should never happen — game state is invalid if hand is empty mid-play.
            raise ValueError(
                f"AI {self.seat.name}: hand is empty during PLAYING phase — "
                "likely a deal bug (check deck.deal gives 8 cards per player)."
            )
        if not legal:
            # legal_cards is empty only if the hand is empty (caught above) or
            # if there's a dealing/legal-cards regression. Earlier versions
            # silently fell back to the full hand, which let illegal-card
            # bugs slip past the AI silently. Raise loudly instead.
            raise AssertionError(
                f"AI {self.seat.name}: legal_cards empty during PLAYING "
                f"(trump={state.trump}, lead={state.current_trick[0] if state.current_trick else None}, "
                f"hand_size={len(hand)}) — likely a legal_cards regression."
            )

        if self.difficulty == Difficulty.EASY:
            return self._easy_play(state, legal)
        if self.difficulty == Difficulty.MEDIUM:
            return self._medium_play(state, legal)
        return self._hard_play(state, legal)
