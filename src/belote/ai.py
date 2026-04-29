from __future__ import annotations

import random
from enum import Enum

from .deck import Card, Rank, Suit, trick_rank
from .deck import card_points as card_points_fn

# trick_rank(Card(trump, Rank.NINE), trump) == 8 + 6 == 14 for any trump
_NINE_TRUMP_RANK = 14
from .game import (
    GameState,
    Phase,
    Seat,
    TrickCard,
    _current_trick_winner,
    legal_cards,
    partner,
)


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AIMemory:
    """Tracks information about played cards and inferred voids."""

    def __init__(self) -> None:
        self.played: set[Card] = set()
        self.known_voids: dict[Seat, set[Suit]] = {}
        self.partner_hand: set[Card] = set()


class AIPlayer:
    def __init__(self, seat: Seat, difficulty: Difficulty = Difficulty.MEDIUM) -> None:
        self.seat = seat
        self.difficulty = difficulty
        self.memory = AIMemory()
        self._rng = random.Random()

    def update_memory(self, state: GameState) -> None:
        """Update memory with currently visible information."""
        if len(state.completed_tricks) == 0 and len(state.current_trick) == 0:
            # New round - reset memory
            self.memory.played.clear()
            self.memory.known_voids.clear()
            self.memory.partner_hand.clear()

        # Track all cards in completed tricks
        for trick in state.completed_tricks:
            for tc in trick:
                self.memory.played.add(tc.card)
        for tc in state.current_trick:
            self.memory.played.add(tc.card)

        # Partner's hand is visible (for NS team, South sees North's plays)
        # In this implementation, AI tracks what it can see
        p = partner(self.seat)
        if state.phase in (Phase.PLAYING, Phase.SCORING):
            # Partner's remaining cards
            for card in state.hand_of(p):
                self.memory.partner_hand.add(card)

    def decide_bid(self, state: GameState) -> Suit | None:
        """Decide whether to bid and which suit."""
        hand = state.hand_of(self.seat)
        forbidden = state.up_card.suit if state.up_card else None

        if self.difficulty == Difficulty.EASY:
            bid = self._easy_bid(hand)
        elif self.difficulty == Difficulty.MEDIUM:
            bid = self._medium_bid(hand, state)
        else:
            bid = self._hard_bid(hand, state)

        if state.bidding_round == 1:
            # Round 1: only take the up-card's suit
            if forbidden and bid == forbidden:
                return bid
            return None
        # Round 2: pick any suit except the forbidden one; try second-best if needed
        if forbidden and bid == forbidden:
            if self.difficulty == Difficulty.EASY:
                return self._easy_bid(hand, exclude=forbidden)
            elif self.difficulty == Difficulty.MEDIUM:
                return self._medium_bid(hand, state, exclude=forbidden)
            else:
                return self._hard_bid(hand, state, exclude=forbidden)
        return bid

    def decide_card(self, state: GameState) -> Card:
        """Decide which card to play."""
        hand = state.hand_of(self.seat)
        legal = legal_cards(state, self.seat)

        if not hand:
            # Should never happen — game state is invalid if hand is empty mid-play.
            raise ValueError(
                f"AI {self.seat.name}: hand is empty during PLAYING phase — "
                "likely a deal bug (check deck.deal gives 8 cards per player)."
            )
        if not legal:
            # Defensive: legal_cards should never be empty mid-play.
            # Fall back to full hand rather than constructing a phantom card.
            # The old fallback Card(Suit.SPADES, Rank.ACE) caused crashes when
            # that card wasn't in the player's hand.
            legal = hand

        if self.difficulty == Difficulty.EASY:
            return self._easy_play(state, legal)
        if self.difficulty == Difficulty.MEDIUM:
            return self._medium_play(state, legal)
        return self._hard_play(state, legal)

    # ---- Easy AI ----

    def _easy_bid(self, hand: tuple[Card, ...], exclude: Suit | None = None) -> Suit | None:
        """Bid if hand has >= 2 trump honors (J, 9, A) in any suit."""
        honors = {Rank.JACK, Rank.NINE, Rank.ACE}
        for suit in Suit:
            if suit == exclude:
                continue
            count = sum(1 for c in hand if c.suit == suit and c.rank in honors)
            if count >= 2:
                return suit
        return None

    def _easy_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """Uniform random over legal moves."""
        return self._rng.choice(legal)

    # ---- Medium AI ----

    def _medium_bid(self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None) -> Suit | None:
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

        avail = [s for s in Suit if s != exclude]
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

        # Update void inferences
        self._update_voids(state)

        if not trick:
            # Leading
            return self._medium_lead(legal, trump, state)

        lead_card = trick[0].card
        lead_suit = lead_card.suit
        p = partner(self.seat)

        # Check if partner is winning
        current_winner = _current_trick_winner(
            [tc for tc in trick if tc.seat != self.seat], trump, lead_suit
        )
        partner_winning = current_winner is not None and current_winner == p

        if partner_winning and lead_suit != trump:
            # Partner winning, discard low
            return min(legal, key=lambda c: trick_rank(c, trump))

        if lead_suit == trump:
            # Trump led
            my_trumps = [c for c in legal if c.suit == trump]
            if my_trumps:
                if current_winner is not None and current_winner == p:
                    # Partner winning trump, play lowest trump
                    return min(my_trumps, key=lambda c: trick_rank(c, trump))
                # Try to win if we can afford it
                return max(my_trumps, key=lambda c: trick_rank(c, trump))
            # No trumps, discard low non-trump
            return min(legal, key=lambda c: card_points_fn(c, trump))

        # Non-trump led
        my_suit = [c for c in legal if c.suit == lead_suit]
        if my_suit:
            # Must follow
            if current_winner is not None and current_winner == p:
                return min(my_suit, key=lambda c: trick_rank(c, trump))
            return max(my_suit, key=lambda c: trick_rank(c, trump))

        # Void - must trump or discard
        my_trumps = [c for c in legal if c.suit == trump]
        if my_trumps:
            return max(my_trumps, key=lambda c: trick_rank(c, trump))

        return min(legal, key=lambda c: card_points_fn(c, trump))

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

        # 2. Lead from longest non-trump suit (to establish it)
        non_trumps = [c for c in legal if c.suit != trump]
        if non_trumps:
            suit_counts = {s: sum(1 for c in non_trumps if c.suit == s) for s in Suit if s != trump}
            best_suit = max(suit_counts, key=lambda s: suit_counts[s])
            if suit_counts[best_suit] > 1:
                suit_cards = [c for c in non_trumps if c.suit == best_suit]
                # Lead the highest card of that suit
                return max(suit_cards, key=lambda c: trick_rank(c, trump))

        # 3. Lead lowest trump to pull if we have many
        trumps = [c for c in legal if c.suit == trump]
        if len(trumps) >= 3:
            return min(trumps, key=lambda c: trick_rank(c, trump))

        # 4. Fallback: lead lowest non-trump
        if non_trumps:
            return min(non_trumps, key=lambda c: trick_rank(c, trump))

        if trumps:
            return min(trumps, key=lambda c: trick_rank(c, trump))

        return legal[0]

    # ---- Hard AI ----

    def _hard_bid(self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None) -> Suit | None:
        """Monte-Carlo-lite bidding evaluation with personality."""
        suit_scores: dict[Suit, float] = dict.fromkeys(Suit, 0.0)
        personality = self._rng.uniform(-0.8, 0.8)

        for suit in Suit:
            trump_cards = [c for c in hand if c.suit == suit]
            honor_count = sum(1 for c in trump_cards if c.rank in (Rank.JACK, Rank.NINE, Rank.ACE))
            point_total = sum(card_points_fn(c, suit) for c in trump_cards)

            suit_scores[suit] = point_total * 0.5 + honor_count * 3

            if state.dealer == self.seat or state.dealer == partner(self.seat):
                suit_scores[suit] *= 1.1

            if state.bidding_round == 2 and state.bidder_index >= 2:
                suit_scores[suit] += 1.5

            for other in Suit:
                if other != suit:
                    other_count = sum(1 for c in hand if c.suit == other)
                    if other_count == 0:
                        suit_scores[suit] += 2
                    elif other_count == 1:
                        suit_scores[suit] += 1

        avail = [s for s in Suit if s != exclude]
        best_suit = max(avail, key=lambda s: suit_scores[s])
        if suit_scores[best_suit] + personality >= 6:
            return best_suit
        return None

    def _hard_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """1-ply lookahead with void inference."""
        trump = state.trump
        trick = state.current_trick

        if not trump:
            return legal[0]

        # Update void inferences from completed tricks
        self._update_voids(state)

        if not trick:
            return self._hard_lead(legal, trump, state)

        lead_suit = trick[0].card.suit
        p = partner(self.seat)

        current_winner = _current_trick_winner(
            [tc for tc in trick if tc.seat != self.seat], trump, lead_suit
        )
        partner_winning = current_winner is not None and current_winner == p

        # Score each legal card by expected outcome
        best_card = legal[0]
        best_score: float = -999.0

        for card in legal:
            score = self._score_card_play(card, state, trump, trick, partner_winning)
            if score > best_score:
                best_score = score
                best_card = card

        return best_card

    def _score_card_play(
        self,
        card: Card,
        state: GameState,
        trump: Suit,
        trick: tuple[TrickCard, ...],
        partner_winning: bool,
    ) -> float:
        """Score a card play decision."""
        score = 0.0
        points = card_points_fn(card, trump)
        rank = trick_rank(card, trump)

        # Base: card point value
        score += points * 0.1

        if not trick:
            # Leading
            if card.suit == trump:
                # Leading trump is generally good for pulling
                score += 2
            elif card.rank == Rank.ACE:
                score += 3
            elif points == 0:
                # Leading waste card
                score += 1
            return score

        lead_suit = trick[0].card.suit

        if partner_winning and lead_suit != trump:
            # Partner winning - discard low value cards
            score -= points * 0.5
            if card.suit != trump:
                score += 1
            return score

        # Try to win the trick
        highest_rank = max((trick_rank(tc.card, trump) for tc in trick), default=-1)
        if rank > highest_rank:
            score += 10  # Winning is valuable

            # 2-PLY: If we are winning now, will the next player beat us?
            if len(trick) < 3:
                next_opp = self.seat.next_seat()
                opp_voids = self.memory.known_voids.get(next_opp, set())
                # trick_rank(J, trump)=15, trick_rank(9, trump)=14
                if (next_opp != partner(self.seat)
                        and lead_suit in opp_voids
                        and trump not in opp_voids
                        and (card.suit != trump or rank < _NINE_TRUMP_RANK)):
                    score -= 5
        elif partner_winning:
            # We aren't winning but partner is. Don't play high unless necessary.
            score -= points * 0.8
        else:
            # We are losing and partner is losing.
            score -= points * 0.2

        # Strand opponent honors: if we know opponent is void in lead suit,
        # playing a low card of lead suit forces them to trump or discard
        opp = self.seat.next_seat()
        if opp in self.memory.known_voids:
            voids = self.memory.known_voids[opp]
            if lead_suit in voids and card.suit == lead_suit:
                score += 3

        return score

    def _hard_lead(
        self, legal: tuple[Card, ...], trump: Suit, state: GameState
    ) -> Card:
        """Strategic lead with void awareness."""
        # Prefer leading suit where opponent is known void
        for card in legal:
            if card.suit != trump:
                opp = self.seat.next_seat()
                if opp in self.memory.known_voids and card.suit in self.memory.known_voids[opp]:
                    return card

        # Lead Ace of non-trump
        for card in legal:
            if card.rank == Rank.ACE and card.suit != trump:
                return card

        # Lead low trump for pulling
        trumps = [c for c in legal if c.suit == trump]
        if trumps:
            return min(trumps, key=lambda c: trick_rank(c, trump))

        # Lead lowest non-trump
        non_trumps = [c for c in legal if c.suit != trump]
        if non_trumps:
            return min(non_trumps, key=lambda c: trick_rank(c, trump))

        return legal[0]

    def _update_voids(self, state: GameState) -> None:
        """Infer voids by scanning all played cards from scratch."""
        for seat in Seat:
            self.memory.known_voids[seat] = set()

        for trick in state.completed_tricks:
            if len(trick) < 2:
                continue
            lead_suit = trick[0].card.suit
            for tc in trick[1:]:
                if tc.card.suit != lead_suit:
                    self.memory.known_voids[tc.seat].add(lead_suit)

        cur = state.current_trick
        if len(cur) >= 2:
            lead_suit = cur[0].card.suit
            for tc in cur[1:]:
                if tc.card.suit != lead_suit:
                    self.memory.known_voids[tc.seat].add(lead_suit)
