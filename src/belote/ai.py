from __future__ import annotations

import random
from collections import Counter
from enum import Enum

from .deck import _NONTRUMP_ORDER, Card, Contract, Rank, Suit, trick_rank
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
from .scoring import card_points_with_modifiers

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
        # (completed_count, current_trick_len, hide_partner_hand) of the
        # last partner_hand rebuild. The partner's hand only changes when
        # they play a card or a new round starts; same memo pattern as
        # `last_voids_key`. The third element (`hide_partner_hand`) is the
        # 4.8.2 L3 addition — invalidates the memo if the boss flag flips.
        self.last_partner_hand_key: tuple[int, int, bool] | None = None
        # 4.9.0 / G2: partner-signal tally per suit. Positive = partner
        # signaled "lead this suit"; negative = "don't". Populated by
        # `_process_trick_signals`; read by `_hard_lead` as a tiebreaker.
        # `signals_emitted` caps how many of our own discards become signals
        # per round (preserves tactical value: max 2 per round).
        self.signals: dict[Suit, int] = dict.fromkeys(Suit, 0)
        self.signals_emitted: int = 0


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
            self.memory.last_partner_hand_key = None
            # 4.9.0 / G2: partner-signal tally and our emit-counter follow
            # the same triple-reset pattern as the void cache.
            for suit in Suit:
                self.memory.signals[suit] = 0
            self.memory.signals_emitted = 0
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
            self.memory.last_partner_hand_key = None

        # Track all cards in completed tricks. N is small (max 32 cards), so
        # the O(N) re-walk is fine and keeps this in sync with the transient
        # current_trick loop below.
        for trick in state.completed_tricks:
            for tc in trick:
                self.memory.played.add(tc.card)
        for tc in state.current_trick:
            self.memory.played.add(tc.card)

        # Partner's hand is visible (for NS team, South sees North's plays).
        # It only changes when partner plays a card (i.e. when
        # (completed_count, current_count) advances). Memo on the same key
        # the void cache uses; skip the rebuild on a no-op repeat call.
        #
        # 4.8.2 (L3): include `hide_partner_hand` in the memo key so the
        # memo invalidates if the boss flag flips mid-round. The flag is
        # set at round start in current code, but the assumption is
        # defensive — a future boss or voucher that toggles visibility
        # mid-round would otherwise see stale cached partner cards.
        hide = bool(state.boss_modifiers.hide_partner_hand)
        partner_key: tuple[int, int, bool] = (completed_count, current_count, hide)
        if self.memory.last_partner_hand_key != partner_key:
            p = partner(self.seat)
            self.memory.partner_hand.clear()
            if state.phase in (Phase.PLAYING, Phase.SCORING) and not hide:
                for card in state.hand_of(p):
                    self.memory.partner_hand.add(card)
            self.memory.last_partner_hand_key = partner_key

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
        from .deck import Rank
        from .game import team_of

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

        3.9.3: card values are evaluated through `card_points_with_modifiers`
        so active zero-rank bosses (jacks_zero / aces_zero / kings_zero /
        tens_zero / ban_clubs) suppress those ranks in the bid heuristic.
        Pre-3.9.3 the raw `card_points` totals made the AI overbid TA on a
        jack-heavy hand under Le Sauvage even though those jacks would score
        zero in actual play.
        """
        bm = state.boss_modifiers
        ta_pts = sum(card_points_with_modifiers(c, Suit.TOUT_ATOUT, bm) for c in hand)
        # The Jack-count bonus is the AI's TA strength signal — drop it if
        # jacks are suppressed.
        jack_bonus = (
            0 if bm.jacks_zero
            else sum(1 for c in hand if c.rank == Rank.JACK) * 6
        )
        ta_score = ta_pts + jack_bonus

        sa_pts = sum(card_points_with_modifiers(c, None, bm) for c in hand)
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
        # La Déluge boss makes 7s and 8s of any suit rank as trump (the two
        # LOWEST trumps — 7 at rank 8, 8 at rank 9, both scoring 0 points;
        # see deck.py::trick_rank and ::card_points). Every ranking / point
        # read in this method must thread `_se` through or the AI under-
        # values trump cards that should beat them.
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
        # 4.1.1: discard tiebreakers must honor zero-rank boss flags (kings_zero,
        # aces_zero, jacks_zero, tens_zero, ban_clubs). Pre-4.1.1 medium AI used
        # raw card_points and would "preserve" a K of trump under kings_zero as
        # if it still scored 20 — picking it as the highest-value card to keep.
        bm = state.boss_modifiers

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

    # ---- Hard AI ----

    def _hard_bid(
        self, hand: tuple[Card, ...], state: GameState, exclude: Suit | None = None
    ) -> Suit | None:
        """Monte-Carlo-lite bidding evaluation with personality."""
        card_suits = [s for s in Suit if s.is_card_suit]
        suit_scores: dict[Suit, float] = dict.fromkeys(card_suits, 0.0)
        personality = self._rng.uniform(-0.8, 0.8)

        # Bucket the hand by suit in a single pass. Pre-3.8.0 each suit-loop
        # iteration re-filtered the hand twice (4 suits × 2 walks), and the
        # inner cross-suit lookup re-counted other suits — 12 hand walks
        # total. Single-pass bucketing collapses that to one walk.
        suit_cards: dict[Suit, list[Card]] = {s: [] for s in card_suits}
        for c in hand:
            if c.suit in suit_cards:
                suit_cards[c.suit].append(c)

        bm = state.boss_modifiers
        # Honors are J/9/A; drop a rank from the count if it's zeroed by a
        # boss flag (3.9.3 — honor-counting was previously boss-blind).
        # 4.6.4: hoisted out of the per-suit loop. The closure was being
        # rebuilt 4× per `_hard_bid` call (once per suit) for no benefit.
        _drop_jacks = bm.jacks_zero
        _drop_aces = bm.aces_zero

        def _is_honor(c: Card) -> bool:
            if c.rank == Rank.JACK and _drop_jacks:
                return False
            if c.rank == Rank.ACE and _drop_aces:
                return False
            return c.rank in (Rank.JACK, Rank.NINE, Rank.ACE)

        for suit in card_suits:
            trump_cards = suit_cards[suit]
            honor_count = sum(1 for c in trump_cards if _is_honor(c))
            point_total = sum(card_points_with_modifiers(c, suit, bm) for c in trump_cards)

            suit_scores[suit] = point_total * 0.5 + honor_count * 3

            if state.dealer == self.seat or state.dealer == partner(self.seat):
                suit_scores[suit] *= 1.1

            if state.bidding_round == 2 and state.bidder_index >= 2:
                suit_scores[suit] += 1.5

            for other in card_suits:
                if other != suit:
                    other_count = len(suit_cards[other])
                    if other_count == 0:
                        suit_scores[suit] += 2
                    elif other_count == 1:
                        suit_scores[suit] += 1

        # 4.1.0: under LesClubsBannis (`ban_clubs`) every clubs trick scores 0,
        # making clubs a suicidal trump. The point-total branch already returns
        # 0 for clubs cards via `card_points_with_modifiers`, but the honor
        # count + cross-suit short-suit bonuses still pushed clubs above the
        # bid threshold on club-honor-heavy hands. Exclude clubs from the
        # candidate list under the flag.
        avail = [s for s in card_suits if s != exclude]
        if bm.ban_clubs:
            avail = [s for s in avail if s != Suit.CLUBS]
        if not avail:
            return None
        best_suit = max(avail, key=lambda s: suit_scores[s])
        if suit_scores[best_suit] + personality >= 6:
            return best_suit
        return None

    def _hard_play(self, state: GameState, legal: tuple[Card, ...]) -> Card:
        """1-ply lookahead with void inference."""
        trump = state.trump
        trick = state.current_trick

        # 4.6.6: Sans Atout now uses a 1-ply lookahead with a non-trump
        # ranking heuristic (based on _NONTRUMP_ORDER), rather than falling
        # back to random play.
        is_sa = state.contract == Contract.SANS_ATOUT

        # Update void inferences from completed tricks
        self._update_voids(state)

        if not trick:
            return self._hard_lead(legal, trump, state)

        lead_suit = trick[0].card.suit
        p = partner(self.seat)
        current_winner = _current_trick_winner(
            [tc for tc in trick if tc.seat != self.seat], trump, lead_suit, self._se, is_sa
        )
        partner_winning = current_winner is not None and current_winner == p

        # Precompute per-call counters used by every scoring branch — pre-3.1.0
        # these were recomputed per candidate card (n×4 walks of the hand and
        # memory.played for each legal card).
        # 4.8.2 (P2): dropped redundant `from collections import Counter`
        # local import — `Counter` is already imported at module top.
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
        elif trump is None:
            # Sans Atout: there is no trump suit, so opp_trumps is moot.
            # Setting every count to 0 makes `opp_trumps = max(0, 8) = 8`,
            # but the heuristic branches keyed off `opp_trumps` won't fire
            # anyway because the lookahead falls through to the non-trump
            # ranking path.
            total_trumps = 0
            my_trumps = 0
            played_trumps = 0
            partner_trumps = 0
        else:
            total_trumps = 8
            my_trumps = hand_suit_counts.get(trump, 0)
            played_trumps = sum(1 for c in self.memory.played if c.suit == trump)
            partner_trumps = sum(1 for c in self.memory.partner_hand if c.suit == trump)
        opp_trumps = max(0, total_trumps - my_trumps - played_trumps - partner_trumps)

        # 4.7.1 P1/P2: hoist invariants out of the per-card scoring loop.
        # `highest_rank` and `opp_voids` depend only on (trick, trump, is_sa,
        # self._se, next_opp) — all constant across the 1–8 legal candidates.
        # Recomputing them per card was the dominant cost of `_hard_play`.
        if trick:
            highest_rank = max(
                (
                    trick_rank(tc.card, trump, self._se)
                    if not is_sa
                    else _NONTRUMP_ORDER[tc.card.rank]
                    for tc in trick
                    if not is_sa or tc.card.suit == trick[0].card.suit
                ),
                default=-1,
            )
        else:
            highest_rank = -1
        next_opp = self.seat.next_seat()
        opp_voids = self.memory.known_voids.get(next_opp, set())

        # 4.8.2 (P1): pre-compute per-candidate rank once. `_score_winning_strategy`
        # called `trick_rank(card, trump, self._se)` once for the candidate and
        # again for every visible partner card on every legal candidate
        # iteration — O(legal × partner_hand) recomputations. Building dicts
        # here collapses that to O(legal + partner_hand) lookups.
        # Under SA, off-suit candidates get rank -1 (B1 short-circuit) so they
        # cannot win the trick; lead-suit candidates use `_NONTRUMP_ORDER`.
        lead_suit_for_ranks = trick[0].card.suit if trick else None
        if is_sa:
            candidate_ranks: dict[Card, int] = {
                c: (_NONTRUMP_ORDER[c.rank] if c.suit == lead_suit_for_ranks else -1)
                for c in legal
            }
            partner_ranks: dict[Card, int] = {
                c: _NONTRUMP_ORDER[c.rank] for c in self.memory.partner_hand
            }
        else:
            candidate_ranks = {c: trick_rank(c, trump, self._se) for c in legal}
            partner_ranks = {
                c: trick_rank(c, trump, self._se) for c in self.memory.partner_hand
            }

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
                is_sa=is_sa,
                highest_rank=highest_rank,
                opp_voids=opp_voids,
                card_rank=candidate_ranks[card],
                partner_ranks=partner_ranks,
            )
            if score > best_score:
                best_score = score
                best_card = card

        # 4.9.0 / G2: on forced discards, optionally swap rank within the
        # chosen 0-point set (7/8/9) to signal partner. No tactical change
        # (same suit, same point value); capped at 2 emits per round.
        return self._maybe_signal_swap(best_card, legal, state, trump)

    def _maybe_signal_swap(
        self,
        best_card: Card,
        legal: tuple[Card, ...],
        state: GameState,
        trump: Suit | None,
    ) -> Card:
        """4.9.0 / G2: peter-convention signal swap.

        When `best_card` is a forced off-suit non-trump discard AND we have
        2+ same-suit 0-point alternatives, swap to the high (9 = "lead this
        suit back") or low (7 = "don't") variant based on whether we hold
        a high non-trump (A/10) in that suit. Hard tier only; capped at
        2 emits per round (`memory.signals_emitted`) so we don't sacrifice
        all rank flexibility for signaling.
        """
        if self.difficulty != Difficulty.HARD:
            return best_card
        if self.memory.signals_emitted >= 2:
            return best_card
        trick = state.current_trick
        if not trick:
            return best_card  # leading, not a discard
        lead_suit = trick[0].card.suit
        if best_card.suit == lead_suit:
            return best_card  # followed suit, not a discard
        if trump is not None and best_card.suit == trump:
            return best_card  # we trumped
        if trump == Suit.TOUT_ATOUT:
            return best_card  # every suit is trump
        # Same-suit 0-point alternatives among legal cards.
        candidates = [
            c for c in legal
            if c.suit == best_card.suit
            and c.rank in (Rank.SEVEN, Rank.EIGHT, Rank.NINE)
        ]
        if len(candidates) < 2:
            return best_card
        # Direction: "like" iff we still hold a non-trump A or 10 in that
        # suit (a strong card worth leading toward).
        my_hand = state.hand_of(self.seat)
        likes = any(
            c.suit == best_card.suit and c.rank in (Rank.ACE, Rank.TEN)
            for c in my_hand
        )
        order = {Rank.SEVEN: 0, Rank.EIGHT: 1, Rank.NINE: 2}
        if likes:
            chosen = max(candidates, key=lambda c: order[c.rank])
        else:
            chosen = min(candidates, key=lambda c: order[c.rank])
        if chosen != best_card:
            self.memory.signals_emitted += 1
        return chosen

    def _score_card_play(
        self,
        card: Card,
        state: GameState,
        trump: Suit | None,
        trick: tuple[TrickCard, ...],
        partner_winning: bool,
        hand_suit_counts: dict[Suit, int],
        my_trumps: int,
        opp_trumps: int,
        is_sa: bool = False,
        highest_rank: int = -1,
        opp_voids: set[Suit] | None = None,
        *,
        card_rank: int | None = None,
        partner_ranks: dict[Card, int] | None = None,
    ) -> float:
        """Score a card play decision with advanced heuristics.

        4.8.2 (P1): `card_rank` and `partner_ranks` are pre-computed by
        `_hard_play` once per call and threaded through so the per-candidate
        recomputation of `trick_rank` / `_NONTRUMP_ORDER` is gone. Both
        default to `None` for standalone callers (tests) — the downstream
        helper falls back to deriving them itself.
        """
        score = 0.0
        # 4.1.1: per-card point value must honor zero-rank boss flags
        # (kings_zero / aces_zero / jacks_zero / tens_zero / ban_clubs).
        # Propagates to _score_discarding_strategy / _score_winning_strategy
        # via the `points` parameter and to _score_leading_strategy via `bm`.
        bm = state.boss_modifiers
        points = card_points_with_modifiers(card, trump, bm)
        # Small per-card tiebreaker: when win/loss heuristics are otherwise
        # equal, slightly bias toward playing the higher-value card. The
        # 0.1 coefficient keeps this strictly subordinate to the win/loss
        # bonuses (~+5 to ~-9) below.
        score += points * 0.1

        if not trick:
            return self._score_leading_strategy(
                card, trump, my_trumps, opp_trumps, bm, points=points, is_sa=is_sa
            )

        if partner_winning and trick[0].card.suit != (trump if not is_sa else None):
            return self._score_discarding_strategy(card, trump, points, hand_suit_counts, is_sa=is_sa)

        return self._score_winning_strategy(
            card,
            state,
            trump,
            trick,
            partner_winning,
            points,
            is_sa=is_sa,
            highest_rank=highest_rank,
            opp_voids=opp_voids,
            card_rank=card_rank,
            partner_ranks=partner_ranks,
        )

    def _score_leading_strategy(
        self,
        card: Card,
        trump: Suit | None,
        my_trumps: int,
        opp_trumps: int,
        bm: object,
        *,
        points: int,
        is_sa: bool = False,
    ) -> float:
        """Heuristics for when we are leading the trick."""
        score = 0.0
        if not is_sa and card.suit == trump:
            # Leading trump is good for pulling if opponents still have them
            if opp_trumps > my_trumps:
                score += 4
            else:
                score += 1
        elif card.rank == Rank.ACE:
            score += 5
        elif points == 0:
            # Leading waste card to probe (4.7.1 P3: reuse caller's already-
            # computed `points` instead of recomputing card_points_with_modifiers
            # — the caller already paid for it on the per-card scoring line).
            score += 2
        return score

    def _score_discarding_strategy(
        self, card: Card, trump: Suit | None, points: int, hand_suit_counts: dict[Suit, int], is_sa: bool = False
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
        trump: Suit | None,
        trick: tuple[TrickCard, ...],
        partner_winning: bool,
        points: int,
        is_sa: bool = False,
        *,
        highest_rank: int | None = None,
        opp_voids: set[Suit] | None = None,
        card_rank: int | None = None,
        partner_ranks: dict[Card, int] | None = None,
    ) -> float:
        """Heuristics for trying to win the trick or ducking.

        4.7.1: `highest_rank` and `opp_voids` are hoisted out of the
        per-legal-card loop in `_hard_play` and passed in. They depend only
        on (trick, trump, is_sa, self._se) and the next-opp seat — all
        constant across the legal-card scoring sweep, so recomputing them
        per card was pure waste. Both default to `None` so standalone
        callers (tests, ad-hoc heuristics) can omit them and the function
        will derive them itself.

        4.8.2 (P1): `card_rank` and `partner_ranks` are similarly hoisted.
        `card_rank` is the candidate's pre-computed rank under the active
        scale (`trick_rank` or `_NONTRUMP_ORDER`, with the B1 off-suit-SA
        short-circuit baked in). `partner_ranks` is the rank lookup for
        every visible card in `self.memory.partner_hand`. Both default to
        `None` so standalone callers (tests) can omit them; the function
        derives them itself.
        """
        score = 0.0
        lead_suit = trick[0].card.suit
        # B1 (4.8.2): under Sans Atout an off-suit card cannot win the trick
        # (per `_card_beats` in game.py). Pin `rank = -1` for off-suit
        # candidates so `rank > highest_rank` is unreachable — pre-4.8.2 an
        # off-suit Ace got rank=7 against highest_rank≤7 (lead-suit only) and
        # fired `win_bonus`, causing the AI to dump high off-suit cards under
        # SA when forced to discard.
        if card_rank is not None:
            rank = card_rank
        elif is_sa and card.suit != lead_suit:
            rank = -1
        elif is_sa:
            rank = _NONTRUMP_ORDER[card.rank]
        else:
            rank = trick_rank(card, trump, self._se)
        is_last_trick = len(state.completed_tricks) == 7
        if highest_rank is None:
            highest_rank = max(
                (
                    trick_rank(tc.card, trump, self._se)
                    if not is_sa
                    else _NONTRUMP_ORDER[tc.card.rank]
                    for tc in trick
                    if not is_sa or tc.card.suit == lead_suit
                ),
                default=-1,
            )
        if opp_voids is None:
            opp_voids = self.memory.known_voids.get(self.seat.next_seat(), set())
        p = partner(self.seat)

        if rank > highest_rank:
            win_bonus = 15 if is_last_trick else 10  # Prioritize Dix de Der
            score += win_bonus

            # 2-PLY: If we are winning now, will the next player beat us?
            # B2 (4.8.2): suppressed under Sans Atout — there is no trump,
            # so opponents cannot trump our winner; the entire heuristic is
            # moot. Pre-4.8.2 it fired (since `None not in opp_voids` is True
            # and `card.suit != trump` is always True under SA), incorrectly
            # penalizing winning plays by -8.
            if not is_sa and len(trick) < 3:
                next_opp = self.seat.next_seat()
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

        # BelAtro awareness: If partner's hand is visible (Le Carnet / shared-
        # void trust tier) AND partner holds a strictly stronger card in the
        # same suit, prefer not to burn our own high card here — partner can
        # cover the trick. 4.6.4: pre-fix this checked `card in partner_hand`
        # which was always False (deck has 32 unique cards, hands are
        # disjoint) so the heuristic never fired. Compare by rank within the
        # same suit using the active trick scale (honours trump rotation
        # under L'Anarchie via the `_se` flag).
        #
        # 4.7.1 B1: mirror the `is_sa` branch above so Sans Atout uses
        # `_NONTRUMP_ORDER` consistently. `trick_rank(card, None, ...)`
        # happens to fall through to the same ordering today, but the SA
        # path is the canonical one and any future divergence in trick_rank
        # would silently break this heuristic.
        #
        # 4.8.2 (P1): rank lookups thread through `partner_ranks` (built
        # once in `_hard_play`) and the candidate's own `card_rank` is now
        # the canonical per-call rank. We compare against partner cards in
        # the same suit using the SAME scale we used for the candidate — so
        # for an off-suit-SA candidate (rank=-1) the comparison degrades to
        # "any same-suit partner card strictly stronger" which is always
        # true; harmless because the candidate doesn't win the trick.
        if self.memory.partner_hand:
            if is_sa:
                my_rank = _NONTRUMP_ORDER[card.rank]
            else:
                my_rank = rank if card_rank is not None else trick_rank(card, trump, self._se)
            for partner_card in self.memory.partner_hand:
                if partner_card.suit != card.suit:
                    continue
                if partner_ranks is not None and partner_card in partner_ranks:
                    partner_rank = partner_ranks[partner_card]
                elif is_sa:
                    partner_rank = _NONTRUMP_ORDER[partner_card.rank]
                else:
                    partner_rank = trick_rank(partner_card, trump, self._se)
                if partner_rank > my_rank:
                    score -= 5
                    break

        return score

    def _hard_lead(
        self, legal: tuple[Card, ...], trump: Suit | None, state: GameState
    ) -> Card:
        """Strategic lead with void awareness.

        4.6.6: `trump` is `Suit | None` to accommodate Sans Atout, where there
        is no trump. The `card.suit != trump` comparisons degrade gracefully
        when `trump` is `None` (every card is treated as non-trump), so the
        function returns a sensible lead in both cases.

        4.9.0 / G2: when partner has signaled a "lead this suit" preference
        (`memory.signals[suit] > 0`) and we hold a non-trump card in that
        suit, prefer it. Inserted before the void-based bias so an explicit
        partner signal outweighs an inferred void.
        """
        # 4.9.0 / G2: honor partner's signal first (HARD tier only — only
        # HARD AI populates the signals dict).
        if self.difficulty == Difficulty.HARD:
            liked = {s for s, v in self.memory.signals.items() if v > 0}
            for card in legal:
                if card.suit in liked and card.suit != trump:
                    return card

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
        trump = state.trump
        while self.memory.processed_tricks_count < completed_count:
            trick = state.completed_tricks[self.memory.processed_tricks_count]
            self._process_trick_voids(trick, wild_active)
            # 4.9.0 / G2: read partner's signals from completed tricks only.
            # Current-trick signals are partial (partner may not have played
            # yet) and would update mid-decision — only completed tricks are
            # stable.
            if self.difficulty == Difficulty.HARD:
                self._process_trick_signals(trick, trump)
            self.memory.processed_tricks_count += 1

        # 2. Process current trick (transient, so we don't increment processed_tricks_count)
        self._process_trick_voids(state.current_trick, wild_active)
        self.memory.last_voids_key = key

    def _process_trick_signals(
        self, trick: tuple[TrickCard, ...], trump: Suit | None
    ) -> None:
        """4.9.0 / G2: scan a trick for partner's signal cards.

        A partner play counts as a signal when it is an off-suit, non-trump
        7/8/9 (zero-point card). Rank 9 = "lead this suit"; 7 = "don't";
        8 is neutral. Tally accrues in `memory.signals[suit]` and is read
        by `_hard_lead` as a tiebreaker.
        """
        if len(trick) < 2 or trump == Suit.TOUT_ATOUT:
            return
        p = partner(self.seat)
        lead_suit = trick[0].card.suit
        for tc in trick[1:]:
            if tc.seat != p:
                continue
            if tc.card.suit == lead_suit:
                continue  # followed suit — not a signal
            if trump is not None and tc.card.suit == trump:
                continue  # partner trumped — not a signal
            if tc.card.rank == Rank.NINE:
                self.memory.signals[tc.card.suit] += 1
            elif tc.card.rank == Rank.SEVEN:
                self.memory.signals[tc.card.suit] -= 1
            # Rank.EIGHT is neutral — no tally change.

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
