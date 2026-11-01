"""Medium AI: point-count bidding, trick-winning play and simple leads."""

from __future__ import annotations

from collections import Counter

from ..deck import Card, Contract, Rank, Suit, trick_rank
from ..game import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
    _current_trick_winner,
    partner,
)
from ..scoring import card_points_with_modifiers
from .easy import EasyMixin


class MediumMixin(EasyMixin):
    def _medium_special(
        self, hand: tuple[Card, ...], state: GameState, lengths: dict[Suit, int]
    ) -> BidValue:
        """Weighted score: TA leans on Jacks (each acts like a trump master in
        its own suit), SA leans on Aces and 10s with a flat-distribution bonus."""
        personality = self._rng.uniform(-0.5, 0.5)

        # TA score: every honor counts because every suit is trump.
        ta_weights = {Rank.JACK: 4.0, Rank.NINE: 3.0, Rank.ACE: 2.0, Rank.KING: 1.0}
        ta_score = sum(ta_weights.get(c.rank, 0.0) for c in hand)
        # Spread bonus: more suits with honors → TA stronger.
        suits_with_honors = len({c.suit for c in hand if c.rank in ta_weights})
        ta_score += 0.5 * suits_with_honors

        # SA score: Aces and 10s win lead-suit tricks; flat distribution helps.
        sa_weights = {Rank.ACE: 3.0, Rank.TEN: 2.0, Rank.KING: 1.0}
        sa_score = sum(sa_weights.get(c.rank, 0.0) for c in hand)
        if max(lengths.values(), default=0) <= 3 and min(lengths.values(), default=8) >= 1:
            sa_score += 1.5  # flat-distribution bonus

        # Thresholds: TA needs ~12 weighted points (Jack+Ace+9 in two suits etc.)
        # SA needs ~9 (three Aces). Scaled to be slightly under classic-suit
        # threshold so TA/SA show up in distinct hands.
        ta_pick = ta_score + personality >= 11.0
        sa_pick = sa_score + personality >= 9.0
        if ta_pick and (not sa_pick or ta_score >= sa_score):
            return Suit.TOUT_ATOUT
        if sa_pick:
            return SANS_ATOUT_BID
        return None

    def _medium_bid(
        self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None
    ) -> Suit | None:
        """Heuristic score per suit with personality variance."""
        suit_scores: dict[Suit, float] = dict.fromkeys(Suit, 0.0)
        honor_values = {
            Rank.JACK: 4.0,
            Rank.NINE: 3.0,
            Rank.ACE: 2.0,
            Rank.KING: 1.0,
            Rank.QUEEN: 1.0,
        }

        personality = self._rng.uniform(-0.5, 0.5)

        for card in hand:
            if card.rank in honor_values:
                suit_scores[card.suit] += honor_values[card.rank]
            suit_scores[card.suit] += 0.1

        aggression = 0.0
        if state.bidding_round == 2 and state.bidder_index == 3:
            aggression = 1.0

        avail = [s for s in Suit if s != exclude and s.is_card_suit]
        best_suit = max(avail, key=lambda s: suit_scores[s])
        if suit_scores[best_suit] + personality + aggression >= 4:
            return best_suit
        return None

    def _medium_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """Strategic play: lead high, cover partner, duck when winning."""
        trump = state.trump
        if trump is None:
            return self._easy_play(state, legal)
        trick = state.current_trick
        # 4.1.1: discard tiebreakers must honor zero-rank boss flags (kings_zero,
        # aces_zero, jacks_zero, tens_zero, ban_clubs). Pre-4.1.1 medium AI used
        # raw card_points and would "preserve" a K of trump under kings_zero as
        # if it still scored 20 — picking it as the highest-value card to keep.
        bm = state.variants

        # Update void inferences
        self._update_voids(state)

        if not trick:
            # Leading
            return self._medium_lead(legal, trump, state)

        # 4.8.1: cache trick_rank per card so each min/max walk is O(n) lookups
        # rather than O(n) recomputations. Same for card_points_with_modifiers
        # in the discard branches.
        ranks = {c: trick_rank(c, trump, self._se) for c in legal}

        lead_card = trick[0].card
        lead_suit = lead_card.suit
        p = partner(self.seat)

        # Check if partner is winning
        is_sa = state.contract == Contract.SANS_ATOUT
        current_winner = _current_trick_winner(
            [tc for tc in trick if tc.seat != self.seat], trump, lead_suit, self._se, is_sa
        )
        partner_winning = current_winner is not None and current_winner == p

        if partner_winning and lead_suit != trump:
            # Partner winning, discard low
            return min(legal, key=ranks.__getitem__)

        if lead_suit == trump:
            # Trump led
            my_trumps = [c for c in legal if c.suit == trump]
            if my_trumps:
                if current_winner is not None and current_winner == p:
                    # Partner winning trump, play lowest trump
                    return min(my_trumps, key=ranks.__getitem__)
                # Try to win if we can afford it
                return max(my_trumps, key=ranks.__getitem__)
            # No trumps, discard low non-trump
            return min(legal, key=lambda c: card_points_with_modifiers(c, trump, bm))

        # Non-trump led
        my_suit = [c for c in legal if c.suit == lead_suit]
        if my_suit:
            # Must follow
            if current_winner is not None and current_winner == p:
                return min(my_suit, key=ranks.__getitem__)
            return max(my_suit, key=ranks.__getitem__)

        # Void - must trump or discard
        my_trumps = [c for c in legal if c.suit == trump]
        if my_trumps:
            # Optimized: pick the lowest trump that wins the trick
            # (or the lowest trump if we can't win)
            highest_in_trick = max(
                (trick_rank(tc.card, trump, self._se) for tc in trick), default=-1
            )
            winners = [c for c in my_trumps if ranks[c] > highest_in_trick]
            if winners:
                return min(winners, key=ranks.__getitem__)
            return min(my_trumps, key=ranks.__getitem__)

        return min(legal, key=lambda c: card_points_with_modifiers(c, trump, bm))

    def _medium_lead(self, legal: tuple[Card, ...], trump: Suit | None, state: GameState) -> Card:
        """Lead strategy: void forcing, high non-trump A, longest suit, then trump pulls."""
        if not trump:
            return legal[0]

        # 0. Try to lead suit where next opponent is known void (to force trumping/discarding)
        opp = self.seat.next_seat()
        if opp in self.memory.known_voids:
            voids = self.memory.known_voids[opp]
            for card in legal:
                if card.suit != trump and card.suit in voids:
                    return card

        # 1. Try to lead Ace of non-trump suit (safe lead)
        for card in legal:
            if card.rank == Rank.ACE and card.suit != trump:
                return card

        # 2. Lead from longest non-trump suit (to establish it).
        # 4.6.5: pre-fix walked `non_trumps` 3× — once to build, once per suit
        # inside the dict-comprehension `sum(...)`, then again to filter by
        # `best_suit`. Counter collapses that to a single pass; `most_common`
        # also returns the count so we skip the second lookup.
        non_trumps = [c for c in legal if c.suit != trump]
        if non_trumps:
            suit_counts = Counter(c.suit for c in non_trumps if c.suit.is_card_suit)
            best_suit, best_n = suit_counts.most_common(1)[0]
            if best_n > 1:
                suit_cards = [c for c in non_trumps if c.suit == best_suit]
                # Lead the highest card of that suit
                return max(suit_cards, key=lambda c: trick_rank(c, trump, self._se))

        # 3. Lead lowest trump to pull if we have many
        trumps = [c for c in legal if c.suit == trump]
        if len(trumps) >= 3:
            return min(trumps, key=lambda c: trick_rank(c, trump, self._se))

        # 4. Fallback: lead lowest non-trump
        if non_trumps:
            return min(non_trumps, key=lambda c: trick_rank(c, trump, self._se))

        if trumps:
            return min(trumps, key=lambda c: trick_rank(c, trump, self._se))

        return legal[0]
