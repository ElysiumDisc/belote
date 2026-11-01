"""AI core: difficulty levels, card memory, void/signal tracking.

Shared by every difficulty tier (`easy.py`, `medium.py`, `hard.py`); the
public `AIPlayer` that dispatches between them lives in `player.py`.
"""

from __future__ import annotations

import random
from enum import Enum

from ..deck import Card, Rank, Suit
from ..game import (
    GameState,
    Phase,
    Seat,
    TrickCard,
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


class AIBase:
    """Seat, RNG and the per-round memory every tier reads."""

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
        # Set per decide_card() call from state.variants.seven_eight_trump.
        # All ranking helpers in this class read it via self._se.
        self._se = False

    def _reset_round_memory(self) -> None:
        """Clear all per-round derived memory back to a clean slate.

        Shared by the new-round and mid-round-undo paths in ``update_memory`` so
        the two can't drift: a partial reset (e.g. clearing the void cache but
        not the partner-signal tally) would let ``_update_voids`` re-walk the
        surviving tricks and double-count their signals.
        """
        self.memory.played.clear()
        for s in Seat:
            self.memory.known_voids[s].clear()
        self.memory.partner_hand.clear()
        self.memory.processed_tricks_count = 0
        self.memory.last_voids_key = None
        self.memory.last_partner_hand_key = None
        # 4.9.0 / G2: partner-signal tally and our emit-counter follow
        # the same reset pattern as the void cache.
        for suit in Suit:
            self.memory.signals[suit] = 0
        self.memory.signals_emitted = 0

    def update_memory(self, state: GameState) -> None:
        """Update memory with currently visible information."""
        completed_count = len(state.completed_tricks)
        current_count = len(state.current_trick)

        if completed_count == 0 and current_count == 0:
            # New round - reset memory. Including the void-cache key — without
            # this a (0, 0) / (0, 1) key from the first decision of *this* round
            # could coincidentally match a leftover from the previous round and
            # cause _update_voids to skip processing entirely.
            self._reset_round_memory()
        elif (
            self.memory.last_voids_key is not None
            and (completed_count, current_count) < self.memory.last_voids_key
        ):
            # Mid-round undo: the state regressed below the highest point
            # we've processed. `known_voids` and `processed_tricks_count`
            # are monotonic and would carry stale inferences forward
            # (a void inferred from a now-rolled-back trick). Rebuild from
            # the current state instead of trying to subtract. The signal
            # tally is rebuilt by _update_voids' re-walk (processed count is
            # reset to 0), so it MUST be cleared here too — otherwise the
            # surviving tricks' signals are double-counted. Same full reset
            # as a new round.
            self._reset_round_memory()

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
        hide = bool(state.variants.hide_partner_hand)
        partner_key: tuple[int, int, bool] = (completed_count, current_count, hide)
        if self.memory.last_partner_hand_key != partner_key:
            p = partner(self.seat)
            self.memory.partner_hand.clear()
            if state.phase in (Phase.PLAYING, Phase.SCORING) and not hide:
                for card in state.hand_of(p):
                    self.memory.partner_hand.add(card)
            self.memory.last_partner_hand_key = partner_key

    @staticmethod
    def _suit_lengths(hand: tuple[Card, ...]) -> dict[Suit, int]:
        lengths: dict[Suit, int] = dict.fromkeys((s for s in Suit if s.is_card_suit), 0)
        for c in hand:
            if c.suit in lengths:
                lengths[c.suit] += 1
        return lengths

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
        wild_active = state.variants.wild_seven_eight

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

    def _process_trick_signals(self, trick: tuple[TrickCard, ...], trump: Suit | None) -> None:
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

    def _process_trick_voids(self, trick: tuple[TrickCard, ...], wild_active: bool = False) -> None:
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
