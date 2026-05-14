from __future__ import annotations

import random
from enum import Enum

from .deck import Card, Contract, Rank, Suit, trick_rank
from .deck import card_points as card_points_fn
from .game import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
    Phase,
    Seat,
    TrickCard,
    _current_trick_winner,
    legal_cards,
    partner,
)

# trick_rank(Card(trump, Rank.NINE), trump) == 8 + 6 == 14 for any trump
_NINE_TRUMP_RANK = 14


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AIMemory:
    """Tracks information about played cards and inferred voids."""

    def __init__(self) -> None:
        self.played: set[Card] = set()
        self.known_voids: dict[Seat, set[Suit]] = {s: set() for s in Seat}
        self.partner_hand: set[Card] = set()
        self.processed_tricks_count: int = 0
        # (completed_count, current_trick_len) of the last _update_voids call.
        # Lets us skip re-scanning a stable transient trick on each decision.
        self.last_voids_key: tuple[int, int] | None = None


class AIPlayer:
    def __init__(
        self,
        seat: Seat,
        difficulty: Difficulty = Difficulty.MEDIUM,
        rng: random.Random | None = None,
    ) -> None:
        self.seat = seat
        self.difficulty = difficulty
        self.memory = AIMemory()
        # Accept the caller's seeded RNG (round driver / replay tooling) so
        # easy-AI plays, personality jitter, and any other stochastic AI
        # decisions are reproducible under a fixed seed. Falls back to an
        # unseeded Random() for legacy callers that construct an AIPlayer
        # directly (e.g. test fixtures).
        self._rng = rng if rng is not None else random.Random()
        # Set per decide_card() call from state.boss_modifiers.seven_eight_trump.
        # All ranking helpers in this class read it via self._se.
        self._se = False

    def update_memory(self, state: GameState) -> None:
        """Update memory with currently visible information."""
        completed_count = len(state.completed_tricks)
        current_count = len(state.current_trick)

        if completed_count == 0 and current_count == 0:
            # New round - reset memory. Including the void-cache key — without
            # this a (0, 0) / (0, 1) key from the first decision of *this* round
            # could coincidentally match a leftover from the previous round and
            # cause _update_voids to skip processing entirely.
            self.memory.played.clear()
            for s in Seat:
                self.memory.known_voids[s].clear()
            self.memory.partner_hand.clear()
            self.memory.processed_tricks_count = 0
            self.memory.last_voids_key = None
        elif (
            self.memory.last_voids_key is not None
            and (completed_count, current_count) < self.memory.last_voids_key
        ):
            # Mid-round undo: the state regressed below the highest point
            # we've processed. `known_voids` and `processed_tricks_count`
            # are monotonic and would carry stale inferences forward
            # (a void inferred from a now-rolled-back trick). Rebuild from
            # the current state instead of trying to subtract.
            self.memory.played.clear()
            for s in Seat:
                self.memory.known_voids[s].clear()
            self.memory.processed_tricks_count = 0
            self.memory.last_voids_key = None

        # Track all cards in completed tricks
        for trick in state.completed_tricks:
            for tc in trick:
                self.memory.played.add(tc.card)
        for tc in state.current_trick:
            self.memory.played.add(tc.card)

        # Partner's hand is visible (for NS team, South sees North's plays)
        # In this implementation, AI tracks what it can see
        p = partner(self.seat)
        self.memory.partner_hand.clear()
        if (
            state.phase in (Phase.PLAYING, Phase.SCORING)
            and not state.boss_modifiers.hide_partner_hand
        ):
            for card in state.hand_of(p):
                self.memory.partner_hand.add(card)

    def decide_bid(self, state: GameState) -> BidValue:
        """Decide whether to bid and which contract.

        Returns a normal Suit, `Suit.TOUT_ATOUT`, the `SANS_ATOUT_BID` string,
        or None (pass). TA and SA are only considered in round 2; round 1 is
        "take the up-card suit at the standard contract" only.
        """
        self._se = state.boss_modifiers.seven_eight_trump
        # Boss: La Solitude (Partner forced pass)
        if state.boss_modifiers.partner_forced_pass and self.seat == partner(Seat.SOUTH):
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

    @staticmethod
    def _suit_lengths(hand: tuple[Card, ...]) -> dict[Suit, int]:
        lengths: dict[Suit, int] = dict.fromkeys(
            (s for s in Suit if s.is_card_suit), 0
        )
        for c in hand:
            if c.suit in lengths:
                lengths[c.suit] += 1
        return lengths

    def _easy_special(
        self, hand: tuple[Card, ...], lengths: dict[Suit, int]
    ) -> BidValue:
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

    def _hard_special(
        self, hand: tuple[Card, ...], state: GameState, lengths: dict[Suit, int]
    ) -> BidValue:
        """Use actual card_points scales as the heuristic.

        TA: every card scores on the trump scale; threshold against the average
            taker total (~62 raw). Plus a Jack-count bonus.
        SA: every card scores on the non-trump scale; flat-Aces hand favored.
        """
        ta_pts = sum(card_points_fn(c, Suit.TOUT_ATOUT) for c in hand)
        jack_bonus = sum(1 for c in hand if c.rank == Rank.JACK) * 6  # Jacks dominate TA
        ta_score = ta_pts + jack_bonus

        sa_pts = sum(card_points_fn(c, None) for c in hand)
        # Long suits are bad under SA — opponents won't follow your suit.
        long_suit_penalty = sum(max(0, n - 3) ** 2 for n in lengths.values()) * 4
        sa_score = sa_pts - long_suit_penalty

        # Aggression bonus when last to bid in round 2 (won't get another shot).
        aggression = 6 if state.bidder_index == 3 else 0

        # Calibrated thresholds: average 8-card hand has ~31 points raw on each
        # scale. We want TA/SA to fire on noticeably stronger-than-average hands.
        if ta_score + aggression >= 50:
            return Suit.TOUT_ATOUT
        if sa_score + aggression >= 38:
            return SANS_ATOUT_BID
        return None

    def decide_card(self, state: GameState) -> Card:
        """Decide which card to play."""
        hand = state.hand_of(self.seat)
        legal = legal_cards(state, self.seat)
        # La Déluge boss promotes 7s/8s of trump above the Jack — every ranking
        # / point read in this method must respect that flag or the AI will
        # pick the wrong cards.
        self._se = state.boss_modifiers.seven_eight_trump

        # Boss: L'Agent Double (Partner sabotages on 3 random tricks)
        if state.boss_modifiers.agent_double_active and self.seat == partner(Seat.SOUTH):
            current_trick = len(state.completed_tricks) + 1
            raw_tricks = state._joker_state.get("agent_double_tricks", frozenset())
            sabotage_tricks: frozenset[int] = (
                raw_tricks if isinstance(raw_tricks, frozenset) else frozenset()
            )
            trump = state.trump
            if current_trick in sabotage_tricks and trump is not None:
                return min(legal, key=lambda c: trick_rank(c, trump, self._se))

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
            if suit == exclude or not suit.is_card_suit:
                continue
            count = sum(1 for c in hand if c.suit == suit and c.rank in honors)
            if count >= 2:
                return suit
        return None

    def _easy_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """Uniform random over legal moves."""
        return self._rng.choice(legal)

    # ---- Medium AI ----

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

        # Update void inferences
        self._update_voids(state)

        if not trick:
            # Leading
            return self._medium_lead(legal, trump, state)

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
            return min(legal, key=lambda c: trick_rank(c, trump, self._se))

        if lead_suit == trump:
            # Trump led
            my_trumps = [c for c in legal if c.suit == trump]
            if my_trumps:
                if current_winner is not None and current_winner == p:
                    # Partner winning trump, play lowest trump
                    return min(my_trumps, key=lambda c: trick_rank(c, trump, self._se))
                # Try to win if we can afford it
                return max(my_trumps, key=lambda c: trick_rank(c, trump, self._se))
            # No trumps, discard low non-trump
            return min(legal, key=lambda c: card_points_fn(c, trump, self._se))

        # Non-trump led
        my_suit = [c for c in legal if c.suit == lead_suit]
        if my_suit:
            # Must follow
            if current_winner is not None and current_winner == p:
                return min(my_suit, key=lambda c: trick_rank(c, trump, self._se))
            return max(my_suit, key=lambda c: trick_rank(c, trump, self._se))

        # Void - must trump or discard
        my_trumps = [c for c in legal if c.suit == trump]
        if my_trumps:
            # Optimized: pick the lowest trump that wins the trick
            # (or the lowest trump if we can't win)
            highest_in_trick = max(
                (trick_rank(tc.card, trump, self._se) for tc in trick), default=-1
            )
            winners = [c for c in my_trumps if trick_rank(c, trump, self._se) > highest_in_trick]
            if winners:
                return min(winners, key=lambda c: trick_rank(c, trump, self._se))
            return min(my_trumps, key=lambda c: trick_rank(c, trump, self._se))

        return min(legal, key=lambda c: card_points_fn(c, trump, self._se))

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
            suit_counts = {
                s: sum(1 for c in non_trumps if c.suit == s)
                for s in Suit
                if s != trump and s.is_card_suit
            }
            best_suit = max(suit_counts, key=lambda s: suit_counts[s])
            if suit_counts[best_suit] > 1:
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

    # ---- Hard AI ----

    def _hard_bid(
        self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None
    ) -> Suit | None:
        """Monte-Carlo-lite bidding evaluation with personality."""
        card_suits = [s for s in Suit if s.is_card_suit]
        suit_scores: dict[Suit, float] = dict.fromkeys(card_suits, 0.0)
        personality = self._rng.uniform(-0.8, 0.8)

        for suit in card_suits:
            trump_cards = [c for c in hand if c.suit == suit]
            honor_count = sum(1 for c in trump_cards if c.rank in (Rank.JACK, Rank.NINE, Rank.ACE))
            point_total = sum(card_points_fn(c, suit, self._se) for c in trump_cards)

            suit_scores[suit] = point_total * 0.5 + honor_count * 3

            if state.dealer == self.seat or state.dealer == partner(self.seat):
                suit_scores[suit] *= 1.1

            if state.bidding_round == 2 and state.bidder_index >= 2:
                suit_scores[suit] += 1.5

            for other in card_suits:
                if other != suit:
                    other_count = sum(1 for c in hand if c.suit == other)
                    if other_count == 0:
                        suit_scores[suit] += 2
                    elif other_count == 1:
                        suit_scores[suit] += 1

        avail = [s for s in card_suits if s != exclude]
        best_suit = max(avail, key=lambda s: suit_scores[s])
        if suit_scores[best_suit] + personality >= 6:
            return best_suit
        return None

    def _hard_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """1-ply lookahead with void inference."""
        trump = state.trump
        trick = state.current_trick

        if not trump:
            # Sans Atout: the lookahead scoring uses `trick_rank(c, trump, ...)`
            # which is meaningless without a trump suit. Fall back to easy
            # (random over legal) rather than `legal[0]` so we don't degrade
            # to a fully deterministic worst-case under SA — matches what
            # `_medium_play` does at its own trump==None guard.
            return self._easy_play(state, legal)

        # Update void inferences from completed tricks
        self._update_voids(state)

        if not trick:
            return self._hard_lead(legal, trump, state)

        lead_suit = trick[0].card.suit
        p = partner(self.seat)

        is_sa = state.contract == Contract.SANS_ATOUT
        current_winner = _current_trick_winner(
            [tc for tc in trick if tc.seat != self.seat], trump, lead_suit, self._se, is_sa
        )
        partner_winning = current_winner is not None and current_winner == p

        # Precompute per-call counters used by every scoring branch — pre-3.1.0
        # these were recomputed per candidate card (n×4 walks of the hand and
        # memory.played for each legal card).
        from collections import Counter

        my_hand = state.hand_of(self.seat)
        hand_suit_counts: dict[Suit, int] = Counter(c.suit for c in my_hand)
        # Under Tout Atout every card is a trump; under a normal contract
        # trump cards are those matching the trump suit. `opp_trumps` must
        # subtract everything that is no longer in opponents' hands: my own
        # trumps, trumps already played, and any of partner's visible
        # trumps (empty under `hide_partner_hand`).
        if trump is Suit.TOUT_ATOUT:
            total_trumps = 32
            my_trumps = len(my_hand)
            played_trumps = len(self.memory.played)
            partner_trumps = len(self.memory.partner_hand)
        else:
            total_trumps = 8
            my_trumps = hand_suit_counts.get(trump, 0)
            played_trumps = sum(1 for c in self.memory.played if c.suit == trump)
            partner_trumps = sum(1 for c in self.memory.partner_hand if c.suit == trump)
        opp_trumps = max(0, total_trumps - my_trumps - played_trumps - partner_trumps)

        # Score each legal card by expected outcome
        best_card = legal[0]
        best_score: float = -999.0

        for card in legal:
            score = self._score_card_play(
                card,
                state,
                trump,
                trick,
                partner_winning,
                hand_suit_counts,
                my_trumps,
                opp_trumps,
            )
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
        hand_suit_counts: dict[Suit, int],
        my_trumps: int,
        opp_trumps: int,
    ) -> float:
        """Score a card play decision with advanced heuristics."""
        score = 0.0
        points = card_points_fn(card, trump, self._se)
        # Base: card point value (prefer keeping high value cards if not winning)
        score += points * 0.1

        if not trick:
            return self._score_leading_strategy(card, trump, my_trumps, opp_trumps)

        if partner_winning and trick[0].card.suit != trump:
            return self._score_discarding_strategy(card, trump, points, hand_suit_counts)

        return self._score_winning_strategy(card, state, trump, trick, partner_winning, points)

    def _score_leading_strategy(
        self, card: Card, trump: Suit, my_trumps: int, opp_trumps: int
    ) -> float:
        """Heuristics for when we are leading the trick."""
        score = 0.0
        if card.suit == trump:
            # Leading trump is good for pulling if opponents still have them
            if opp_trumps > my_trumps:
                score += 4
            else:
                score += 1
        elif card.rank == Rank.ACE:
            score += 5
        elif card_points_fn(card, trump, self._se) == 0:
            # Leading waste card to probe
            score += 2
        return score

    def _score_discarding_strategy(
        self, card: Card, trump: Suit, points: int, hand_suit_counts: dict[Suit, int]
    ) -> float:
        """Heuristics for when partner is winning and we can discard."""
        score = 0.0
        # Partner winning - discard strategy
        score -= points * 0.7  # Penalize throwing away points

        # Prefer discarding from short suits (to establish voids)
        if hand_suit_counts.get(card.suit, 0) == 1:
            score += 3

        # Prefer keeping cards that partner is void in (to trump later)
        p = partner(self.seat)
        if card.suit in self.memory.known_voids.get(p, set()):
            score -= 2
        return score

    def _score_winning_strategy(
        self,
        card: Card,
        state: GameState,
        trump: Suit,
        trick: tuple[TrickCard, ...],
        partner_winning: bool,
        points: int,
    ) -> float:
        """Heuristics for trying to win the trick or ducking."""
        score = 0.0
        rank = trick_rank(card, trump, self._se)
        is_last_trick = len(state.completed_tricks) == 7
        highest_rank = max((trick_rank(tc.card, trump, self._se) for tc in trick), default=-1)
        lead_suit = trick[0].card.suit
        p = partner(self.seat)

        if rank > highest_rank:
            win_bonus = 15 if is_last_trick else 10  # Prioritize Dix de Der
            score += win_bonus

            # 2-PLY: If we are winning now, will the next player beat us?
            if len(trick) < 3:
                next_opp = self.seat.next_seat()
                opp_voids = self.memory.known_voids.get(next_opp, set())
                if (
                    next_opp != p
                    and lead_suit in opp_voids
                    and trump not in opp_voids
                    and (card.suit != trump or rank < _NINE_TRUMP_RANK)
                ):
                    # Opponent likely to trump us
                    score -= 8
        elif partner_winning:
            # We aren't winning but partner is. Duck low.
            score -= points * 0.9
            if card.suit != trump:
                score += 2
        else:
            # We are losing and partner is losing.
            score -= points * 0.4

        # BelAtro awareness: If partner's hand is visible, don't duplicate strength.
        if card in self.memory.partner_hand:
            score -= 5

        return score

    def _hard_lead(self, legal: tuple[Card, ...], trump: Suit, state: GameState) -> Card:
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
            return min(trumps, key=lambda c: trick_rank(c, trump, self._se))

        # Lead lowest non-trump
        non_trumps = [c for c in legal if c.suit != trump]
        if non_trumps:
            return min(non_trumps, key=lambda c: trick_rank(c, trump, self._se))

        return legal[0]

    def _update_voids(self, state: GameState) -> None:
        """Infer voids incrementally."""
        # Skip the work if neither the completed-count nor the current-trick
        # length has changed since last call (decide_card may run multiple
        # times for the same trick during e.g. lookahead exploration).
        completed_count = len(state.completed_tricks)
        key = (completed_count, len(state.current_trick))
        if self.memory.last_voids_key == key:
            return

        # Le Républicain (or any deck/voucher that sets the flag): 7s and 8s
        # are wild and may be played on any suit, so an off-suit 7/8 doesn't
        # prove void in lead suit.
        wild_active = bool(state._joker_state.get("republicain_wild"))

        # 1. Process new completed tricks
        while self.memory.processed_tricks_count < completed_count:
            trick = state.completed_tricks[self.memory.processed_tricks_count]
            self._process_trick_voids(trick, wild_active)
            self.memory.processed_tricks_count += 1

        # 2. Process current trick (transient, so we don't increment processed_tricks_count)
        self._process_trick_voids(state.current_trick, wild_active)
        self.memory.last_voids_key = key

    def _process_trick_voids(
        self, trick: tuple[TrickCard, ...], wild_active: bool = False
    ) -> None:
        """Analyze a trick for voids."""
        if len(trick) < 2:
            return
        lead_suit = trick[0].card.suit
        for tc in trick[1:]:
            if tc.card.suit != lead_suit:
                # Under republicain_wild a 7 or 8 may be played on any suit,
                # so an off-suit 7/8 doesn't prove void in the lead suit.
                if wild_active and tc.card.rank in (Rank.SEVEN, Rank.EIGHT):
                    continue
                self.memory.known_voids[tc.seat].add(lead_suit)
