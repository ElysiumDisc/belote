"""Hard AI: scored card play (lead / win / discard strategies), signal
swaps and full-memory leads."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from ..deck import _NONTRUMP_ORDER, Card, Contract, Rank, Suit, is_trump_card, trick_rank
from ..game import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
    TrickCard,
    _current_trick_winner,
    partner,
)
from ..scoring import card_points_with_modifiers
from .base import _NINE_TRUMP_RANK, AIBase, Difficulty


class HardMixin(AIBase):
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
        bm = state.variants
        ta_pts = sum(card_points_with_modifiers(c, Suit.TOUT_ATOUT, bm) for c in hand)
        # The Jack-count bonus is the AI's TA strength signal — drop it if
        # jacks are suppressed.
        jack_bonus = 0 if bm.jacks_zero else sum(1 for c in hand if c.rank == Rank.JACK) * 6
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

        bm = state.variants
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
            suit_scores[suit] = self._hard_suit_score(suit, suit_cards, state, _is_honor)

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

    def _hard_suit_score(
        self,
        suit: Suit,
        suit_cards: dict[Suit, list[Card]],
        state: GameState,
        is_honor: Callable[[Card], bool],
    ) -> float:
        """One candidate trump's bid score: points + honors, dealer-side and
        late-bidder nudges, then short-suit (void/singleton) ruffing bonuses.
        The float operations run in a fixed order — seeded games depend on
        the exact result near the bid threshold."""
        trump_cards = suit_cards[suit]
        honor_count = sum(1 for c in trump_cards if is_honor(c))
        point_total = sum(card_points_with_modifiers(c, suit, state.variants) for c in trump_cards)

        score = point_total * 0.5 + honor_count * 3
        if state.dealer == self.seat or state.dealer == partner(self.seat):
            score *= 1.1
        if state.bidding_round == 2 and state.bidder_index >= 2:
            score += 1.5
        for other, cards in suit_cards.items():
            if other != suit:
                if not cards:
                    score += 2
                elif len(cards) == 1:
                    score += 1
        return score

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
        lead_suit_for_ranks = trick[0].card.suit if trick else None
        se = self._se

        def _rank_in_trick(c: Card) -> int:
            """Strength of `c` in the current trick; -1 if it cannot take it.

            Mirrors `game._card_beats`: a card contends only if it follows the
            led suit or is a real trump (trump suit, or 7/8 under Déluge).
            Off-suit cards never win under Sans Atout or Tout Atout. Without
            this, an off-suit A (non-trump rank 7) "beat" a led K (rank 5),
            so Hard AI dumped aces to the opponents expecting to win.
            """
            if lead_suit_for_ranks is not None and c.suit != lead_suit_for_ranks:
                if is_sa or trump is Suit.TOUT_ATOUT:
                    return -1
                if not is_trump_card(c, trump, se):
                    return -1
            return _NONTRUMP_ORDER[c.rank] if is_sa else trick_rank(c, trump, se)

        highest_rank = max((_rank_in_trick(tc.card) for tc in trick), default=-1)
        next_opp = self.seat.next_seat()
        opp_voids = self.memory.known_voids.get(next_opp, set())

        # 4.8.2 (P1): pre-compute per-candidate rank once. `_score_winning_strategy`
        # called `trick_rank(card, trump, self._se)` once for the candidate and
        # again for every visible partner card on every legal candidate
        # iteration — O(legal × partner_hand) recomputations. Building dicts
        # here collapses that to O(legal + partner_hand) lookups.
        candidate_ranks: dict[Card, int] = {c: _rank_in_trick(c) for c in legal}
        if is_sa:
            partner_ranks: dict[Card, int] = {
                c: _NONTRUMP_ORDER[c.rank] for c in self.memory.partner_hand
            }
        else:
            partner_ranks = {c: trick_rank(c, trump, self._se) for c in self.memory.partner_hand}

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
            c
            for c in legal
            if c.suit == best_card.suit and c.rank in (Rank.SEVEN, Rank.EIGHT, Rank.NINE)
        ]
        if len(candidates) < 2:
            return best_card
        # Direction: "like" iff we still hold a non-trump A or 10 in that
        # suit (a strong card worth leading toward).
        my_hand = state.hand_of(self.seat)
        likes = any(c.suit == best_card.suit and c.rank in (Rank.ACE, Rank.TEN) for c in my_hand)
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
        bm = state.variants
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
            return self._score_discarding_strategy(
                card, trump, points, hand_suit_counts, is_sa=is_sa
            )

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
        self,
        card: Card,
        trump: Suit | None,
        points: int,
        hand_suit_counts: dict[Suit, int],
        is_sa: bool = False,
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
            if self._partner_holds_stronger(card, my_rank, trump, is_sa, partner_ranks):
                score -= 5

        return score

    def _partner_holds_stronger(
        self,
        card: Card,
        my_rank: int,
        trump: Suit | None,
        is_sa: bool,
        partner_ranks: dict[Card, int] | None,
    ) -> bool:
        """True if the visible partner hand has a strictly stronger card in
        `card`'s suit (same rank scale as `my_rank`)."""
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
                return True
        return False

    def _hard_lead(self, legal: tuple[Card, ...], trump: Suit | None, state: GameState) -> Card:
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
