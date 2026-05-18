from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ..items.base import Joker, JokerResult
    from .round_ledger import RoundLedger

from belote.deck import Rank, Suit
from belote.game import GameState, Seat

from ..engine.event_bus import (
    BeloteAnnouncedEvent,
    BidMadeEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)

_NS_TEAM = {Seat.SOUTH, Seat.NORTH}

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

    4.6.2: per-event `dataclasses.replace(GameState, ...)` is eliminated.
    A `RoundLedger` holds chips/mult/money mutably and is sealed to a
    canonical immutable GameState exactly once at round end. The ledger's
    joker_state dict is shared (same object) with `state._joker_state`
    via a single `replace()` at round start, so classic-Belote read sites
    (ai.py, scoring.py, game.py) see live mutations without further
    replaces. See `src/belote/belatro/core/round_ledger.py` for the design.
    """

    deck_id: str = "classique"
    carnet_active: bool = False
    partner_jokers_double: bool = False
    partner_tier: int = 1  # Phase 2.3 — 0=degraded … 4=elite
    target_score: int = 80
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

    def _make_ledger(self, state: GameState) -> RoundLedger:
        from .round_ledger import RoundLedger
        return RoundLedger(joker_state=dict(state._joker_state))

    def trigger_round_start(self, state: GameState) -> GameState:
        """Initialize joker state at the beginning of a round."""
        self._log.clear()
        # 4.6.2: build the ledger; its joker_state dict will be installed
        # AS state._joker_state below so further mutations need no replace.
        ledger = self._make_ledger(state)
        self._ledger = ledger
        joker_state = ledger.joker_state

        # Inject round context so jokers can read it via state.get(...)
        joker_state["no_dix_de_der"] = state.boss_modifiers.no_dix_de_der
        joker_state["target_score"] = self.target_score
        # 4.5.0: drop any leftover annonce-card sets from a prior round
        # before this round's DeclarationScoredEvents rebuild them. Read by
        # L'Architecte (deck rule) and LeCollectionneur (joker).
        joker_state.pop("_architecte_ns_annonce_cards", None)
        joker_state.pop("_ns_annonce_cards", None)

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

    def update_state(self, state: GameState, event: object) -> GameState:
        """Process an event and return an updated GameState with new score/joker state.

        4.6.2: thin backward-compat wrapper around `process_event` +
        `materialize`. Pre-4.6.2 this method did the per-event
        `dataclasses.replace` that is now eliminated for callers using
        `process_event` directly (round_driver). Tests and external callers
        that still expect a GameState return continue to work unchanged
        because the lazy-init path below stamps the ledger's joker_state
        onto the input state via a one-time `replace`, restoring the
        shared-dict invariant that trigger_round_start would otherwise
        establish.
        """
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

    def process_event(self, state: GameState, event: object) -> None:
        """4.6.2 hot-path entry. Mutates the ledger in place. No `replace()`.

        Caller is responsible for having called `trigger_round_start` first so
        the ledger and `state._joker_state` share the same dict. Subsequent
        reads of `state._joker_state.get(...)` from classic-Belote code see
        live mutations.
        """
        ledger = self._ledger
        assert ledger is not None, (
            "ScoreAccumulator.process_event called before trigger_round_start. "
            "trigger_round_start installs the RoundLedger and shares its "
            "joker_state dict with state._joker_state."
        )
        joker_state = ledger.joker_state

        def _apply(result: JokerResult, source: str) -> None:
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

        def _apply_edition(joker: Any) -> None:
            """3.0.0: Foil/Holo/Polychrome ride along with each successful
            joker trigger. Imported lazily to avoid a circular import via
            base.py at module load."""
            from ..items.base import Edition, JokerResult

            ed = getattr(joker, "edition", Edition.NONE)
            if ed == Edition.FOIL:
                _apply(JokerResult(add_chips=50), source=f"{joker.name} (Foil)")
            elif ed == Edition.HOLO:
                _apply(JokerResult(add_mult=10.0), source=f"{joker.name} (Holo)")
            elif ed == Edition.POLYCHROME:
                _apply(JokerResult(times_mult=1.5), source=f"{joker.name} (Polychrome)")

        def _fire_jokers(method_name: str, event_obj: Any) -> None:
            # 4.6.2: read pre-resolved (joker, method) pairs from the registry
            # so the per-event getattr cascade is gone. Lazy build on first
            # use if a caller forgot to call `attach_jokers` (this also
            # protects tests that mutate `self._jokers` directly).
            if not self._handler_index and self._jokers:
                self.attach_jokers(self._jokers)
            for joker, method in self._handler_index.get(method_name, ()):
                result = method(event_obj, joker_state)
                if not result:
                    continue
                _apply(result, source=joker.name)
                _apply_edition(joker)
                # Phase 2.3: partner-joker tier scaling.
                # tier 0 (degraded) / 1 (base) → just the baseline apply.
                # tier 2 (boost) / 3 (strong) → +1 apply (≈ ×2 effect),
                #                               matches legacy partner_jokers_double at trust ≥ 7.
                # tier 4 (elite) → +2 applies (≈ ×3 effect).
                #
                # `partner_jokers_double` is the legacy boolean flag (pre-3.5.0
                # back-compat for tests that set it directly). When both are
                # set, `max()` picks whichever is larger; a one-shot
                # DeprecationWarning fires so callers migrate to tier. The flag
                # is slated for removal in 4.0; new code should use `partner_tier`.
                if getattr(joker, "is_partner_joker", False):
                    # Clamp to the documented [0, 4] tier range; out-of-band
                    # values from corrupted save state or future mutations
                    # should degrade to the nearest valid tier rather than
                    # crash the round with IndexError.
                    _tier = max(0, min(self.partner_tier, 4))
                    tier_extras = (0, 0, 1, 1, 2)[_tier]
                    if self.partner_jokers_double and tier_extras > 0:
                        import warnings
                        warnings.warn(
                            "ScoreAccumulator.partner_jokers_double is deprecated "
                            "alongside partner_tier; set only one. The flag will "
                            "be removed in 4.0.",
                            DeprecationWarning,
                            stacklevel=2,
                        )
                    extra_applies = max(
                        tier_extras, 1 if self.partner_jokers_double else 0
                    )
                    for _ in range(extra_applies):
                        _apply(result, source=f"{joker.name} (T{self.partner_tier})")

        if isinstance(event, TrickWonEvent):
            # Base chips from card points
            ledger.chips += event.card_points

            # Le Républicain: +5 chips per 7 or 8 in any trick (regardless of winner)
            if self.deck_id == "republicain":
                wilds = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
                if wilds:
                    ledger.chips += wilds * 5
                    self._log.append(f"Républicain: +{wilds * 5} chips ({wilds}× wild)")

            # Le Carnet: +1 Mult when South personally wins a trick
            if self.carnet_active and event.winner == Seat.SOUTH:
                ledger.mult += 1.0
                self._log.append("Le Carnet: +1 Mult (South won trick)")

            # Planet contract_levels bonuses (applied when NS team wins the trick)
            if event.winner in _NS_TEAM and self.contract_levels:
                # Per-suit trump bonuses (Saturn, Venus, Mercury, Jupiter)
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
                # The Moon (Sans Atout): honor bonus per honor won
                if event.trump is None:
                    moon_reward = self.contract_levels.get("sans_atout", {})
                    honor_bonus = moon_reward.get("honor_bonus", 0.0)
                    if honor_bonus:
                        honors = sum(
                            1 for c in event.cards
                            if c.rank in (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.JACK, Rank.NINE)
                        )
                        if honors:
                            bonus_int = int(honors * honor_bonus)
                            ledger.chips += bonus_int
                            self._log.append(f"La Lune: +{bonus_int} chips (honors)")
                # The Sun (Tout Atout): +X Mult per trick beyond the 4th
                if event.trump == Suit.TOUT_ATOUT and event.trick_number > 4:
                    sun_reward = self.contract_levels.get("tout_atout", {})
                    sun_mult = sun_reward.get("bonus_mult_per_trick", 0.0)
                    if sun_mult:
                        ledger.mult += sun_mult
                        self._log.append(
                            f"Le Soleil: +{sun_mult} Mult (trick #{event.trick_number})"
                        )

            # 4.5.0 deck rules — separate from planets (`self.contract_levels`
            # is empty on a fresh run, so these can't share the gate above).
            if event.winner in _NS_TEAM:
                # L'Infiltré: Ghost Lead. When NS wins a trick by playing a
                # Trump on a non-trump lead, the winner must have been void
                # of lead (legal_cards forbids trumping while holding lead).
                # +2 Mult, +$1.
                if joker_state.get("ghost_lead") and event.trump is not None:
                    lead_suit = event.cards[0].suit if event.cards else None
                    # Under TOUT_ATOUT every card is trump, so no play can be
                    # "void of the led suit" — is_trump_lead resolves to True
                    # and the bonus is correctly gated off.
                    is_trump_lead = (
                        lead_suit == event.trump
                        or event.trump == Suit.TOUT_ATOUT
                    )
                    if lead_suit is not None and not is_trump_lead:
                        seat = event.leader_seat
                        for card in event.cards:
                            if seat == event.winner and card.suit == event.trump:
                                ledger.mult += 2.0
                                ledger.money += 1
                                self._log.append(
                                    "L'Infiltré: +2 Mult, +$1 (ghost lead)"
                                )
                                break
                            seat = seat.next_seat()

                # L'Architecte: +$2 on NS-won tricks that contain any card
                # from a declared NS Annonce. The Annonce card-set is
                # stamped into joker_state by the DeclarationScoredEvent
                # branch; we look it up here.
                if joker_state.get("annonce_cash_x2"):
                    ns_annonce_cards = joker_state.get(
                        "_architecte_ns_annonce_cards", frozenset()
                    )
                    if ns_annonce_cards and any(
                        (c.suit.name, c.rank.name) in ns_annonce_cards
                        for c in event.cards
                    ):
                        ledger.money += 2
                        self._log.append("L'Architecte: +$2 (Annonce trick)")

            # Fire all Joker triggers
            _fire_jokers("on_trick_won", event)

        elif isinstance(event, BeloteAnnouncedEvent):
            _fire_jokers("on_belote", event)

        elif isinstance(event, DeclarationScoredEvent):
            ledger.chips += event.points
            # Harvest the NS-team Annonce card-set so downstream consumers
            # (L'Architecte deck rule, LeCollectionneur joker) can check
            # trick membership in O(1) on later TrickWonEvents. Rebuilt from
            # state.declarations on each event — declarations all fire on
            # trick 1 so the cost is paid once. Frozenset of (suit, rank)
            # tuples for hashability and joker_state scalar-only invariant.
            ns_cards: set[tuple[str, str]] = set()
            for d in state.declarations:
                if d.seat not in _NS_TEAM:
                    continue
                detail = d.detail
                cards = getattr(detail, "cards", ()) if detail else ()
                for c in cards:
                    ns_cards.add((c.suit.name, c.rank.name))
            frozen_ns_cards = frozenset(ns_cards)
            # L'Architecte's key is kept for backwards-compat with the deck
            # test that pins it; new consumers read `_ns_annonce_cards`.
            joker_state["_architecte_ns_annonce_cards"] = frozen_ns_cards
            joker_state["_ns_annonce_cards"] = frozen_ns_cards
            _fire_jokers("on_declaration", event)

        elif isinstance(event, RoundEndEvent):
            # Planet contract_levels money bonuses at round end (Mercury)
            if self.contract_levels:
                contract_id = _SUIT_TO_CONTRACT.get(event.trump) if event.trump else None
                if contract_id:
                    reward = self.contract_levels.get(contract_id, {})
                    if reward.get("add_money") and not event.breakdown.is_failed:
                        ledger.money += reward["add_money"]
                        self._log.append(f"Planet ({contract_id}): +${reward['add_money']}")
                # Pluto (Capot bonus)
                if event.capot and not event.breakdown.is_failed:
                    pluto_reward = self.contract_levels.get("capot", {})
                    if pluto_reward.get("capot_bonus"):
                        ledger.chips += pluto_reward["capot_bonus"]
                        self._log.append(f"Pluton: +{pluto_reward['capot_bonus']} chips (capot)")
                # Libra (Coinche): +X Mult per coinche level on success
                if (
                    event.coinche_level > 0
                    and event.taker_seat in _NS_TEAM
                    and not event.breakdown.is_failed
                ):
                    libra_reward = self.contract_levels.get("coinche", {})
                    libra_mult: float = libra_reward.get("coinche_multiplier", 0.0)
                    if libra_mult:
                        libra_bonus: float = libra_mult * event.coinche_level
                        ledger.mult += libra_bonus
                        self._log.append(
                            f"Balance: +{libra_bonus} Mult (coinche×{event.coinche_level})"
                        )
            _fire_jokers("on_round_end", event)

        elif isinstance(event, BidMadeEvent):
            # Inject contract type into joker state so jokers can read it
            joker_state["contract"] = event.contract
            # Re-emits (post-coinche refresh) update derived state but must not
            # re-fire on_bid jokers — those already fired for the original bid.
            if not event.re_emit:
                _fire_jokers("on_bid", event)

        # 4.6.2: no `replace(state, ...)` here — the ledger holds chips/mult/
        # money, and joker_state is the same dict object as state._joker_state
        # (installed at trigger_round_start). seal_round / materialize stamp
        # the values back into a frozen GameState when the caller needs it.

    def materialize(self, state: GameState) -> GameState:
        """Return a sealed GameState with ledger values stamped in.

        Cheap to call (one `replace()` per call). Round_driver invokes this
        at HUD-render boundaries and at round-end. Idempotent within a round:
        calling twice in a row with no intervening `process_event` returns a
        state with identical scalar fields.
        """
        if self._ledger is None:
            return state
        return self._ledger.seal_round(state)

    def seal_round(self, state: GameState) -> GameState:
        """Round-end synonym for `materialize`. Use this at the round boundary
        for readability; semantically identical to `materialize`."""
        return self.materialize(state)

    def _live_chips(self, state: GameState) -> int:
        """Prefer ledger.chips (live mid-round) over state._chips (stale until
        materialize). 4.6.2 — keeps HUD reads cheap without forcing a
        per-render `dataclasses.replace`."""
        if self._ledger is not None:
            return int(self._ledger.chips)
        return int(state._chips)

    def _live_mult(self, state: GameState) -> float:
        if self._ledger is not None:
            return float(self._ledger.mult)
        return float(state._mult)

    def _live_money(self, state: GameState) -> int:
        if self._ledger is not None:
            return int(self._ledger.money)
        return int(state._bonus_money)

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

    def get_popup_lines(self, state: GameState) -> list[str]:
        # Match the clamp in get_total(): L'Égoïste can push _chips negative
        # mid-round; the popup line would otherwise read "Chips -12 × Mult …
        # = 0" which looks like a UI bug rather than the intended clamp.
        chips_display = max(0, self._live_chips(state))
        mult_display = self._live_mult(state)
        return [*self._log, f"Chips {chips_display} × Mult {mult_display:.1f} = {self.get_total(state)}"]

