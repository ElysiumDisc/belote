from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypedDict

from .state import BelatroState, as_belatro

if TYPE_CHECKING:
    from ..items.base import Joker, JokerResult
    from .round_ledger import RoundLedger

from belote.deck import Rank, Suit, is_trump_card
from belote.game import GameState, Seat

from ..engine.event_bus import (
    BeloteAnnouncedEvent,
    BidMadeEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)

_log = logging.getLogger(__name__)

_NS_TEAM = {Seat.SOUTH, Seat.NORTH}

_HONOR_RANKS = (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.JACK, Rank.NINE)

_SUIT_TO_CONTRACT: dict[Suit, str] = {
    Suit.SPADES: "spades",
    Suit.HEARTS: "hearts",
    Suit.DIAMONDS: "diamonds",
    Suit.CLUBS: "clubs",
    Suit.TOUT_ATOUT: "tout_atout",
}


class ContractReward(TypedDict, total=False):
    """Schema for a single entry in `BelAtroRun.contract_levels` (3.6.0).

    Planet items at the shop bump their associated contract's reward — the
    populated keys depend on the planet. `total=False` permits partial
    entries; the TypedDict catches typos (`bonus_mult_per_trick` vs
    `bonus_per_trick`) at type-check time. See `belatro/items/planets.py`
    for the producing site of each key.
    """

    # Per-suit (Saturn / Venus / Mercury / Jupiter): trick-level bonuses
    add_chips: int          # +chips per trick won on this contract
    add_mult: float         # +mult per trick won on this contract (Venus: 0.3)
    jack_9_bonus: int       # +chips per Jack/Nine in a won trick
    # The Moon (Sans Atout)
    honor_bonus: int        # +chips per honor card in a won trick
    # The Sun (Tout Atout)
    bonus_mult_per_trick: float  # +mult per trick past the 4th (Sun: 1.0)
    # Mercury planet round-end
    add_money: int          # money awarded at round-end on success
    # Pluto (Capot)
    capot_bonus: int        # +chips on capot success
    # Libra (Coinche)
    coinche_multiplier: float  # +mult per coinche level on NS success (Libra: 1.0)


@dataclass(slots=True)
class ScoreAccumulator:
    """
    Accumulates Chips and Mult across one round,
    processing Joker triggers as events arrive.

    4.6.2: per-event `dataclasses.replace(BelatroState, ...)` is eliminated.
    A `RoundLedger` holds chips/mult/money mutably and is sealed to a
    canonical immutable BelatroState exactly once at round end. The ledger's
    joker_state dict is shared (same object) with `state._joker_state`
    via a single `replace()` at round start, so classic-Belote read sites
    (ai.py, scoring.py, game.py) see live mutations without further
    replaces. See `src/belote/belatro/core/round_ledger.py` for the design.
    """

    deck_id: str = "classique"
    carnet_active: bool = False
    partner_tier: int = 1  # Phase 2.3 — 0=degraded … 4=elite
    target_score: int = 80
    # 4.7.0: Dix de Der Heist — economy.interest_rate snapshot at round start.
    # Drives the heist reward multiplier `(1 + interest_rate)` when SOUTH wins
    # trick 8 after declaring. Set by `belatro/main.py::_play_blind` next to
    # `target_score`. Symmetric plumbing — heist code reads `self.interest_rate`
    # directly without reaching into `joker_state` for run-level config.
    interest_rate: int = 0
    contract_levels: dict[str, ContractReward] = field(default_factory=dict)
    permanent_chips: int = 0
    permanent_mult: float = 1.0
    _jokers: list[Joker] = field(default_factory=list)
    _log: list[str] = field(default_factory=list)  # for the score popup UI
    # 4.6.2: handler registry — pre-resolved per-event-type joker handler
    # lists, populated in `attach_jokers`. Skips the per-event getattr
    # cascade in `_fire_jokers`. Saves ~50–80μs/round (5 jokers × ~25
    # events × ~0.5μs per getattr).
    _handler_index: dict[str, list[tuple[Joker, Any]]] = field(default_factory=dict)
    # 4.8.2 (B3): identity-set of the jokers passed to the most recent
    # `attach_jokers` call. Compared against `set(map(id, self._jokers))`
    # in `_fire_jokers` to detect post-attach mutation. `None` until the
    # first attach; `set()` after `attach_jokers([])` (which is truthy-
    # distinguishable from None). Excluded from `compare/repr` so test
    # state-equality assertions don't break.
    _attached_joker_ids: set[int] | None = field(default=None, compare=False, repr=False)
    # 4.6.2: RoundLedger lifetime is one round; created in
    # trigger_round_start, sealed in seal_round / materialize. Optional
    # because tests that construct an accumulator without calling
    # trigger_round_start (legacy unit tests for joker handlers) still work
    # via the backward-compat `update_state` wrapper.
    _ledger: RoundLedger | None = None

    _HANDLER_METHODS: tuple[str, ...] = (
        "on_trick_won",
        "on_belote",
        "on_declaration",
        "on_round_end",
        "on_bid",
    )

    def attach_jokers(self, jokers: list[Joker]) -> None:
        self._jokers = jokers
        # Build per-method registry once. Skip handlers that the joker
        # didn't override (i.e. inherits the base Joker.on_X returning
        # None) — `getattr` returns the base-class bound method, but its
        # `__func__` is the same object as Joker.on_X's, so we filter.
        from ..items.base import Joker as _JokerBase

        index: dict[str, list[tuple[Joker, Any]]] = {m: [] for m in self._HANDLER_METHODS}
        for joker in jokers:
            for method_name in self._HANDLER_METHODS:
                method = getattr(joker, method_name, None)
                if method is None:
                    continue
                base_method = getattr(_JokerBase, method_name, None)
                if base_method is not None and getattr(method, "__func__", None) is base_method:
                    continue  # joker didn't override this handler
                index[method_name].append((joker, method))
        self._handler_index = index
        # 4.8.2 (B3): remember exactly which joker objects we registered for so
        # `_fire_jokers` can detect post-attach mutation of `self._jokers` and
        # rebuild before firing. A no-override joker still gets tracked here
        # (so it doesn't trigger spurious rebuilds), even though it has no
        # entries in `_handler_index`.
        self._attached_joker_ids = {id(j) for j in jokers}

    def _make_ledger(self, state: BelatroState) -> RoundLedger:
        from .round_ledger import RoundLedger
        return RoundLedger(joker_state=dict(state._joker_state))

    def trigger_round_start(self, state: GameState) -> BelatroState:
        """Initialize joker state at the beginning of a round.

        Accepts a plain GameState too (upgraded via `as_belatro`)."""
        state = as_belatro(state)
        self._log.clear()
        # 4.6.2: build the ledger; its joker_state dict will be installed
        # AS state._joker_state below so further mutations need no replace.
        ledger = self._make_ledger(state)
        self._ledger = ledger
        joker_state = ledger.joker_state

        # Inject round context so jokers can read it via state.get(...)
        joker_state["no_dix_de_der"] = state.variants.no_dix_de_der
        joker_state["target_score"] = self.target_score
        # 4.5.0: drop any leftover annonce-card sets from a prior round
        # before this round's DeclarationScoredEvents rebuild them. Read by
        # L'Architecte (deck rule) and LeCollectionneur (joker).
        joker_state.pop("_architecte_ns_annonce_cards", None)
        joker_state.pop("_ns_annonce_cards", None)

        # 4.7.0: Dix de Der Heist — per-round transient state.
        #   heist_declared: bool — set True by `round_driver` after the player
        #     accepts the heist prompt. Never set for AI takers.
        #   heist_ns_trick_chips: int — running sum of NS-won card_points over
        #     tricks 1-7. Forfeited (subtracted from `ledger.chips`) if NS does
        #     not win trick 8 with heist active. Scalar (no list) per the
        #     joker_state invariant.
        #   heist_outcome: "won" | "lost" | None — sentinel set on trick-8
        #     resolution so subsequent reads (HUD materialize, etc.) can short-
        #     circuit and so the resolve cannot double-apply.
        joker_state["heist_declared"] = False
        joker_state["heist_ns_trick_chips"] = 0
        joker_state["heist_outcome"] = None

        # Apply permanent bonuses from Tarot cards
        ledger.chips = state._chips + self.permanent_chips
        if self.permanent_mult != 1.0:
            ledger.mult = state._mult * self.permanent_mult
        else:
            ledger.mult = state._mult
        ledger.money = state._bonus_money

        # 4.5.0: on_round_start jokers can now return a JokerResult that
        # adjusts chips/mult/money at round-start. LePrêteur is the first
        # consumer.
        for joker in self._jokers:
            result = joker.on_round_start(joker_state)
            if result is None:
                continue
            if result.add_chips:
                ledger.chips += result.add_chips
                self._log.append(f"{joker.name}: +{result.add_chips} chips")
            if result.add_mult:
                ledger.mult += result.add_mult
                self._log.append(f"{joker.name}: +{result.add_mult} Mult")
            if result.times_mult:
                ledger.mult *= result.times_mult
                self._log.append(f"{joker.name}: ×{result.times_mult} Mult")
            if result.add_money:
                ledger.money += result.add_money
                self._log.append(f"{joker.name}: +${result.add_money}")

        # ONE replace per round-start: install the ledger's joker_state dict
        # AS state._joker_state, and stamp the seeded chips/mult/money.
        # After this, ledger.joker_state IS state._joker_state — classic
        # reads of state._joker_state.get(...) see live mutations.
        return replace(
            state,
            _joker_state=joker_state,
            _chips=ledger.chips,
            _mult=ledger.mult,
            _bonus_money=ledger.money,
        )

    def update_state(self, state: GameState, event: object) -> BelatroState:
        """Process an event and return an updated BelatroState with new score/joker state.

        4.6.2: thin backward-compat wrapper around `process_event` +
        `materialize`. Pre-4.6.2 this method did the per-event
        `dataclasses.replace` that is now eliminated for callers using
        `process_event` directly (round_driver). Tests and external callers
        that still expect a BelatroState return continue to work unchanged
        because the lazy-init path below stamps the ledger's joker_state
        onto the input state via a one-time `replace`, restoring the
        shared-dict invariant that trigger_round_start would otherwise
        establish.
        """
        state = as_belatro(state)
        # Lazily seed a ledger if no trigger_round_start was called — protects
        # legacy unit tests that build a state directly and call update_state.
        if self._ledger is None:
            self._ledger = self._make_ledger(state)
            self._ledger.chips = state._chips
            self._ledger.mult = state._mult
            self._ledger.money = state._bonus_money
            # One-time alias: state._joker_state must point at the same dict
            # the ledger owns, otherwise mutations inside process_event are
            # invisible to subsequent reads of state._joker_state. Caller
            # gets a fresh state with the shared dict installed; their own
            # local reference becomes the new aliased state.
            state = replace(state, _joker_state=self._ledger.joker_state)
        self.process_event(state, event)
        return self.materialize(state)

    def process_event(self, state: BelatroState, event: object) -> None:
        """4.6.2 hot-path entry. Mutates the ledger in place. No `replace()`.

        Caller is responsible for having called `trigger_round_start` first so
        the ledger and `state._joker_state` share the same dict. Subsequent
        reads of `state._joker_state.get(...)` from classic-Belote code see
        live mutations.

        4.10.0: split into one handler per event type (previously a 369-line
        body that rebuilt three closures on every call).
        """
        ledger = self._ledger
        assert ledger is not None, (
            "ScoreAccumulator.process_event called before trigger_round_start. "
            "trigger_round_start installs the RoundLedger and shares its "
            "joker_state dict with state._joker_state."
        )
        if isinstance(event, TrickWonEvent):
            self._on_trick_won(ledger, state, event)
        elif isinstance(event, BeloteAnnouncedEvent):
            self._fire_jokers(ledger, "on_belote", event)
        elif isinstance(event, DeclarationScoredEvent):
            self._on_declaration(ledger, state, event)
        elif isinstance(event, RoundEndEvent):
            self._on_round_end(ledger, event)
        elif isinstance(event, BidMadeEvent):
            # Inject contract type into joker state so jokers can read it.
            ledger.joker_state["contract"] = event.contract
            # Re-emits (post-coinche refresh) update derived state but must not
            # re-fire on_bid jokers — those already fired for the original bid.
            if not event.re_emit:
                self._fire_jokers(ledger, "on_bid", event)
        # 4.6.2: no `replace(state, ...)` here — the ledger holds chips/mult/
        # money, and joker_state is the same dict object as state._joker_state
        # (installed at trigger_round_start). seal_round / materialize stamp
        # the values back into a frozen BelatroState when the caller needs it.

    # ── ledger application helpers ──────────────────────────────────────

    def _apply(self, ledger: RoundLedger, result: JokerResult, source: str) -> None:
        if result.add_chips:
            ledger.chips += result.add_chips
            self._log.append(f"{source}: +{result.add_chips} chips")
        if result.add_mult:
            ledger.mult += result.add_mult
            self._log.append(f"{source}: +{result.add_mult} Mult")
        if result.times_mult:
            ledger.mult *= result.times_mult
            self._log.append(f"{source}: ×{result.times_mult} Mult")
        if result.add_money:
            ledger.money += result.add_money
            self._log.append(f"{source}: +${result.add_money}")

    def _apply_edition(self, ledger: RoundLedger, joker: Joker) -> None:
        """3.0.0: Foil/Holo/Polychrome ride along with each successful joker
        trigger. Imported lazily to avoid a circular import via base.py."""
        from ..items.base import Edition, JokerResult

        ed = getattr(joker, "edition", Edition.NONE)
        if ed == Edition.FOIL:
            self._apply(ledger, JokerResult(add_chips=50), source=f"{joker.name} (Foil)")
        elif ed == Edition.HOLO:
            self._apply(ledger, JokerResult(add_mult=10.0), source=f"{joker.name} (Holo)")
        elif ed == Edition.POLYCHROME:
            self._apply(
                ledger, JokerResult(times_mult=1.5), source=f"{joker.name} (Polychrome)"
            )

    def _fire_jokers(self, ledger: RoundLedger, method_name: str, event_obj: Any) -> None:
        # 4.6.2: read pre-resolved (joker, method) pairs from the registry so
        # the per-event getattr cascade is gone. Lazy build on first use if a
        # caller forgot to call `attach_jokers`.
        #
        # 4.8.2 (B3): also rebuild if the current `_jokers` list differs from
        # the identity-set captured at the most recent attach (catches tests
        # that append to `_jokers` after an empty attach, and any other
        # post-attach mutation).
        if self._attached_joker_ids is None:
            if self._jokers:
                self.attach_jokers(self._jokers)
        elif self._attached_joker_ids != {id(j) for j in self._jokers}:
            self.attach_jokers(self._jokers)
        joker_state = ledger.joker_state
        for joker, method in self._handler_index.get(method_name, ()):
            # 4.6.4: per-joker transactional + EventBus-style isolation. A
            # joker raising mid-dispatch must not leave chips/mult/money/
            # joker_state half-applied nor skip its siblings. self._log is
            # snapshotted too since `_apply` writes to it.
            snap_log_len = len(self._log)
            try:
                with ledger.transactional():
                    result = method(event_obj, joker_state)
                    if not result:
                        continue
                    self._apply(ledger, result, source=joker.name)
                    self._apply_edition(ledger, joker)
                    # Phase 2.3: partner-joker tier scaling.
                    # tier 0 (degraded) / 1 (base) → just the baseline apply.
                    # tier 2 (boost) / 3 (strong) → +1 apply (≈ ×2 effect, trust 5–8).
                    # tier 4 (elite) → +2 applies (≈ ×3 effect).
                    # (The pre-3.5.0 `partner_jokers_double` flag was removed
                    # in 4.10.0; tier fully subsumes it.)
                    if getattr(joker, "is_partner_joker", False):
                        # Clamp to [0, 4] so corrupted save state degrades to
                        # the nearest valid tier instead of an IndexError.
                        tier = max(0, min(self.partner_tier, 4))
                        for _ in range((0, 0, 1, 1, 2)[tier]):
                            self._apply(
                                ledger, result, source=f"{joker.name} (T{self.partner_tier})"
                            )
            except Exception:
                # Roll back any log lines the partial application wrote
                # (the ledger restore is handled by transactional()).
                del self._log[snap_log_len:]
                _log.exception(
                    "Joker %s raised on %s; ledger restored, continuing with siblings.",
                    joker.name, method_name,
                )

    # ── TrickWonEvent ───────────────────────────────────────────────────

    def _on_trick_won(self, ledger: RoundLedger, state: BelatroState, event: TrickWonEvent) -> None:
        # Base chips from card points.
        ledger.chips += event.card_points
        self._trick_deck_bonuses(ledger, event)
        if event.winner in _NS_TEAM:
            if self.contract_levels:
                self._trick_planet_bonuses(ledger, event)
            # 4.5.0 deck rules — separate from planets (`contract_levels` is
            # empty on a fresh run, so these can't share the gate above).
            self._trick_infiltre(ledger, state, event)
            self._trick_architecte(ledger, event)
        # Heist runs BEFORE on_trick_won jokers so trick-8 jokers (LeDernierMot
        # ×2, LExecuteur ×1.5, ...) layer on top of the heisted base. The heist
        # is the player's contract; jokers compose on the realized outcome.
        self._trick_heist(ledger, event)
        self._fire_jokers(ledger, "on_trick_won", event)

    def _trick_deck_bonuses(self, ledger: RoundLedger, event: TrickWonEvent) -> None:
        # Le Républicain: +5 chips per 7 or 8 in any trick (regardless of winner).
        if self.deck_id == "republicain":
            wilds = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
            if wilds:
                ledger.chips += wilds * 5
                self._log.append(f"Républicain: +{wilds * 5} chips ({wilds}× wild)")
        # Le Carnet: +1 Mult when South personally wins a trick.
        if self.carnet_active and event.winner == Seat.SOUTH:
            ledger.mult += 1.0
            self._log.append("Le Carnet: +1 Mult (South won trick)")

    def _trick_planet_bonuses(self, ledger: RoundLedger, event: TrickWonEvent) -> None:
        """Planet contract_levels bonuses on an NS-won trick."""
        # Per-suit trump bonuses (Saturn, Venus, Mercury, Jupiter).
        contract_id = _SUIT_TO_CONTRACT.get(event.trump) if event.trump else None
        if contract_id:
            reward = self.contract_levels.get(contract_id, {})
            if reward.get("add_chips"):
                ledger.chips += reward["add_chips"]
                self._log.append(f"Planet ({contract_id}): +{reward['add_chips']} chips")
            if reward.get("add_mult"):
                ledger.mult += reward["add_mult"]
                self._log.append(f"Planet ({contract_id}): +{reward['add_mult']} Mult")
            if reward.get("jack_9_bonus"):
                count = sum(1 for c in event.cards if c.rank in (Rank.JACK, Rank.NINE))
                if count:
                    bonus = count * reward["jack_9_bonus"]
                    ledger.chips += bonus
                    self._log.append(f"Planet ({contract_id}): +{bonus} chips (J/9)")
        # The Moon (Sans Atout): honor bonus per honor won.
        if event.trump is None:
            # 4.8.2 (B6): int default to match `ContractReward.honor_bonus: int`.
            honor_bonus = self.contract_levels.get("sans_atout", {}).get("honor_bonus", 0)
            if honor_bonus:
                honors = sum(1 for c in event.cards if c.rank in _HONOR_RANKS)
                if honors:
                    bonus_int = int(honors * honor_bonus)
                    ledger.chips += bonus_int
                    self._log.append(f"La Lune: +{bonus_int} chips (honors)")
        # The Sun (Tout Atout): +X Mult per trick beyond the 4th.
        if event.trump == Suit.TOUT_ATOUT and event.trick_number > 4:
            sun_reward = self.contract_levels.get("tout_atout", {})
            sun_mult = sun_reward.get("bonus_mult_per_trick", 0.0)
            if sun_mult:
                ledger.mult += sun_mult
                self._log.append(f"Le Soleil: +{sun_mult} Mult (trick #{event.trick_number})")

    def _trick_infiltre(self, ledger: RoundLedger, state: BelatroState, event: TrickWonEvent) -> None:
        """L'Infiltré (Ghost Lead): NS wins by trumping a non-trump lead (the
        winner must have been void of the lead suit) → +2 Mult, +$1.

        Under Tout Atout every card is trump, so no lead is "non-trump" and the
        bonus is gated off; under La Déluge a led 7/8 is a trump lead.
        """
        if not ledger.joker_state.get("ghost_lead") or event.trump is None or not event.cards:
            return
        lead_card = event.cards[0]
        se = state.variants.seven_eight_trump
        if is_trump_card(lead_card, event.trump, se):
            return
        seat = event.leader_seat
        for card in event.cards:
            if seat == event.winner and card.suit == event.trump:
                ledger.mult += 2.0
                ledger.money += 1
                self._log.append("L'Infiltré: +2 Mult, +$1 (ghost lead)")
                return
            seat = seat.next_seat()

    def _trick_architecte(self, ledger: RoundLedger, event: TrickWonEvent) -> None:
        """L'Architecte: +$2 on NS-won tricks containing a card from a declared
        NS Annonce (card-set stamped by `_on_declaration`)."""
        joker_state = ledger.joker_state
        if not joker_state.get("annonce_cash_x2"):
            return
        ns_annonce_cards = joker_state.get("_architecte_ns_annonce_cards", frozenset())
        if ns_annonce_cards and any(
            (c.suit.name, c.rank.name) in ns_annonce_cards for c in event.cards
        ):
            ledger.money += 2
            self._log.append("L'Architecte: +$2 (Annonce trick)")

    def _trick_heist(self, ledger: RoundLedger, event: TrickWonEvent) -> None:
        """4.7.0 Dix de Der Heist.

        (a) Tricks 1-7 won by NS: accumulate the forfeit basis — the same
            `event.card_points` just added to `ledger.chips`, so a forfeit
            subtracts exactly what was put in regardless of boss modifiers.
        (b) Trick 8 with a heist declared and unresolved: ×(1 + interest_rate)
            Mult on an NS win, or subtract the accumulated chips on an EW win.
            The `heist_outcome` sentinel blocks re-application (the HUD calls
            materialize() ~30× per round, so this must be idempotent).
        """
        joker_state = ledger.joker_state
        if not joker_state.get("heist_declared"):
            return
        if event.winner in _NS_TEAM and event.trick_number <= 7:
            joker_state["heist_ns_trick_chips"] = (
                int(joker_state.get("heist_ns_trick_chips", 0)) + event.card_points
            )
        if not event.is_last or joker_state.get("heist_outcome") is not None:
            return
        if event.winner in _NS_TEAM:
            multiplier = 1 + self.interest_rate
            if multiplier != 1:
                ledger.mult *= float(multiplier)
            joker_state["heist_outcome"] = "won"
            self._log.append(f"Dix de Der HEIST SECURED: ×{multiplier} Mult")
        else:
            forfeit = int(joker_state.get("heist_ns_trick_chips", 0))
            if forfeit:
                ledger.chips -= forfeit
            joker_state["heist_outcome"] = "lost"
            self._log.append(
                f"Dix de Der HEIST BUSTED: -{forfeit} chips (tricks 1-7 forfeited)"
            )

    # ── DeclarationScoredEvent ──────────────────────────────────────────

    def _on_declaration(
        self, ledger: RoundLedger, state: BelatroState, event: DeclarationScoredEvent
    ) -> None:
        ledger.chips += event.points
        # Harvest the NS-team Annonce card-set so L'Architecte (deck rule) and
        # LeCollectionneur (joker) can check trick membership in O(1) on later
        # TrickWonEvents. Frozenset of (suit, rank) name tuples (hashable,
        # satisfies the joker_state scalar-only invariant).
        #
        # 4.6.4: skipped under Le Mime (`declarations_zero`) — those consumers
        # are declaration-derived, so the boss must suppress them too.
        if not state.variants.declarations_zero:
            frozen_ns_cards = frozenset(
                (c.suit.name, c.rank.name)
                for d in state.declarations
                if d.seat in _NS_TEAM and d.detail is not None
                for c in d.detail.cards
            )
            # L'Architecte's key is kept for the deck test that pins it; new
            # consumers read `_ns_annonce_cards`.
            ledger.joker_state["_architecte_ns_annonce_cards"] = frozen_ns_cards
            ledger.joker_state["_ns_annonce_cards"] = frozen_ns_cards
        self._fire_jokers(ledger, "on_declaration", event)

    # ── RoundEndEvent ───────────────────────────────────────────────────

    def _on_round_end(self, ledger: RoundLedger, event: RoundEndEvent) -> None:
        # Planets only level up the player's own (NS) successful contracts.
        ns_success = event.taker_seat in _NS_TEAM and not event.breakdown.is_failed
        if self.contract_levels and ns_success:
            # Mercury & co.: per-contract money bonus.
            contract_id = _SUIT_TO_CONTRACT.get(event.trump) if event.trump else None
            if contract_id:
                reward = self.contract_levels.get(contract_id, {})
                if reward.get("add_money"):
                    ledger.money += reward["add_money"]
                    self._log.append(f"Planet ({contract_id}): +${reward['add_money']}")
            # Pluto (Capot): `event.capot` alone is also True for an EW capot;
            # require an NS capot on an NS contract.
            if event.ns_capot:
                capot_bonus = self.contract_levels.get("capot", {}).get("capot_bonus")
                if capot_bonus:
                    ledger.chips += capot_bonus
                    self._log.append(f"Pluton: +{capot_bonus} chips (capot)")
            # Libra (Coinche): +X Mult per coinche level.
            if event.coinche_level > 0:
                libra_mult: float = self.contract_levels.get("coinche", {}).get(
                    "coinche_multiplier", 0.0
                )
                if libra_mult:
                    libra_bonus: float = libra_mult * event.coinche_level
                    ledger.mult += libra_bonus
                    self._log.append(
                        f"Balance: +{libra_bonus} Mult (coinche×{event.coinche_level})"
                    )
        self._fire_jokers(ledger, "on_round_end", event)

    def materialize(self, state: BelatroState) -> BelatroState:
        """Return a sealed BelatroState with ledger values stamped in.

        Cheap to call (one `replace()` per call). Round_driver invokes this
        at HUD-render boundaries and at round-end. Idempotent within a round:
        calling twice in a row with no intervening `process_event` returns a
        state with identical scalar fields.
        """
        if self._ledger is None:
            return state
        return self._ledger.seal_round(state)

    def seal_round(self, state: BelatroState) -> BelatroState:
        """Round-end synonym for `materialize`. Use this at the round boundary
        for readability; semantically identical to `materialize`."""
        return self.materialize(state)

    def _live_chips(self, state: GameState) -> int:
        """Prefer ledger.chips (live mid-round) over state._chips (stale until
        materialize). 4.6.2 — keeps HUD reads cheap without forcing a
        per-render `dataclasses.replace`."""
        if self._ledger is not None:
            return int(self._ledger.chips)
        return int(as_belatro(state)._chips)

    def _live_mult(self, state: GameState) -> float:
        if self._ledger is not None:
            return float(self._ledger.mult)
        return float(as_belatro(state)._mult)

    def _live_money(self, state: GameState) -> int:
        if self._ledger is not None:
            return int(self._ledger.money)
        return int(as_belatro(state)._bonus_money)

    # Public accessors for the HUD — read these mid-round instead of
    # state._chips / state._mult / state._bonus_money to avoid stale values.
    def current_chips(self, state: GameState) -> int:
        return self._live_chips(state)

    def current_mult(self, state: GameState) -> float:
        return self._live_mult(state)

    def current_money(self, state: GameState) -> int:
        return self._live_money(state)

    def get_total(self, state: GameState) -> int:
        # Clamp at 0: corrupted jokers (L'Égoïste in particular) can subtract
        # chips per trick won by partner, and with enough partner tricks the
        # running total can go negative, producing a negative final score.
        # Final score should never be negative — clamp at the scoring boundary.
        chips: int = max(0, self._live_chips(state))
        mult: float = self._live_mult(state)
        if mult == float(int(mult)):
            return chips * int(mult)
        return int(chips * mult)

    def get_popup_lines(self, state: BelatroState) -> list[str]:
        # Match the clamp in get_total(): L'Égoïste can push _chips negative
        # mid-round; the popup line would otherwise read "Chips -12 × Mult …
        # = 0" which looks like a UI bug rather than the intended clamp.
        chips_display = max(0, self._live_chips(state))
        mult_display = self._live_mult(state)
        return [*self._log, f"Chips {chips_display} × Mult {mult_display:.1f} = {self.get_total(state)}"]

