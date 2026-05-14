from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ..items.base import Joker, JokerResult

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

    def attach_jokers(self, jokers: list[Joker]) -> None:
        self._jokers = jokers

    def trigger_round_start(self, state: GameState) -> GameState:
        """Initialize joker state at the beginning of a round."""
        self._log.clear()
        joker_state = dict(state._joker_state)

        # Inject round context so jokers can read it via state.get(...)
        joker_state["no_dix_de_der"] = state.boss_modifiers.no_dix_de_der
        joker_state["target_score"] = self.target_score

        for joker in self._jokers:
            joker.on_round_start(joker_state)

        # Apply permanent bonuses from Tarot cards
        new_chips = state._chips + self.permanent_chips
        new_mult = state._mult * self.permanent_mult if self.permanent_mult != 1.0 else state._mult

        return replace(state, _joker_state=joker_state, _chips=new_chips, _mult=new_mult)

    def update_state(self, state: GameState, event: object) -> GameState:
        """Process an event and return an updated GameState with new score/joker state.

        Perf note (3.5.0 P3 investigation): the dominant cost (~65% of the
        function) is the final `dataclasses.replace(state, ...)` call. The
        frozen-GameState invariant is load-bearing — many call sites assume
        `state is final_state` once a round is sealed — so we accept the
        replace cost rather than mutating in place. At ~19μs per event and
        ~25 events per round (8 tricks + 2-4 bids + decls + round-end) the
        accumulator contributes ~0.5ms to a full round, well below the
        ~1ms-per-frame budget where it would matter.
        """
        new_chips = state._chips
        new_mult = state._mult
        new_money = state._bonus_money
        # Shallow copy is sufficient: every value written into _joker_state
        # is a scalar (bool / int / str). The pre-3.1.0 deepcopy ran on every
        # event (~20×/round) — see test_joker_state_only_contains_scalar_values
        # in tests/belatro/test_phase1_plumbing.py for the locking invariant.
        joker_state = dict(state._joker_state)

        def _apply(result: JokerResult, source: str) -> None:
            nonlocal new_chips, new_mult, new_money
            if result.add_chips:
                new_chips += result.add_chips
                self._log.append(f"{source}: +{result.add_chips} chips")
            if result.add_mult:
                new_mult += result.add_mult
                self._log.append(f"{source}: +{result.add_mult} Mult")
            if result.times_mult:
                new_mult *= result.times_mult
                self._log.append(f"{source}: ×{result.times_mult} Mult")
            if result.add_money:
                new_money += result.add_money
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
            for joker in self._jokers:
                method = getattr(joker, method_name, None)
                if method:
                    result = method(event_obj, joker_state)
                    if result:
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
                            tier_extras = (0, 0, 1, 1, 2)[self.partner_tier]
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
            new_chips += event.card_points

            # Le Républicain: +5 chips per 7 or 8 in any trick (regardless of winner)
            if self.deck_id == "republicain":
                wilds = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
                if wilds:
                    new_chips += wilds * 5
                    self._log.append(f"Républicain: +{wilds * 5} chips ({wilds}× wild)")

            # Le Carnet: +1 Mult when South personally wins a trick
            if self.carnet_active and event.winner == Seat.SOUTH:
                new_mult += 1.0
                self._log.append("Le Carnet: +1 Mult (South won trick)")

            # Planet contract_levels bonuses (applied when NS team wins the trick)
            if event.winner in _NS_TEAM and self.contract_levels:
                # Per-suit trump bonuses (Saturn, Venus, Mercury, Jupiter)
                contract_id = _SUIT_TO_CONTRACT.get(event.trump) if event.trump else None
                if contract_id:
                    reward = self.contract_levels.get(contract_id, {})
                    if reward.get("add_chips"):
                        new_chips += reward["add_chips"]
                        self._log.append(f"Planet ({contract_id}): +{reward['add_chips']} chips")
                    if reward.get("add_mult"):
                        new_mult += reward["add_mult"]
                        self._log.append(f"Planet ({contract_id}): +{reward['add_mult']} Mult")
                    if reward.get("jack_9_bonus"):
                        count = sum(1 for c in event.cards if c.rank in (Rank.JACK, Rank.NINE))
                        if count:
                            bonus = count * reward["jack_9_bonus"]
                            new_chips += bonus
                            self._log.append(f"Planet ({contract_id}): +{bonus} chips (J/9)")
                # The Moon (Sans Atout): honor bonus per honor won
                if event.trump is None:
                    moon_reward = self.contract_levels.get("sans_atout", {})
                    honor_bonus = moon_reward.get("honor_bonus", 0)
                    if honor_bonus:
                        honors = sum(
                            1 for c in event.cards
                            if c.rank in (Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN, Rank.JACK, Rank.NINE)
                        )
                        if honors:
                            new_chips += honors * honor_bonus
                            self._log.append(f"La Lune: +{honors * honor_bonus} chips (honors)")
                # The Sun (Tout Atout): +X Mult per trick beyond the 4th
                if event.trump == Suit.TOUT_ATOUT and event.trick_number > 4:
                    sun_reward = self.contract_levels.get("tout_atout", {})
                    sun_mult = sun_reward.get("bonus_mult_per_trick", 0)
                    if sun_mult:
                        new_mult += sun_mult
                        self._log.append(
                            f"Le Soleil: +{sun_mult} Mult (trick #{event.trick_number})"
                        )

            # Fire all Joker triggers
            _fire_jokers("on_trick_won", event)

        elif isinstance(event, BeloteAnnouncedEvent):
            _fire_jokers("on_belote", event)

        elif isinstance(event, DeclarationScoredEvent):
            new_chips += event.points
            _fire_jokers("on_declaration", event)

        elif isinstance(event, RoundEndEvent):
            # Planet contract_levels money bonuses at round end (Mercury)
            if self.contract_levels:
                contract_id = _SUIT_TO_CONTRACT.get(event.trump) if event.trump else None
                if contract_id:
                    reward = self.contract_levels.get(contract_id, {})
                    if reward.get("add_money") and not event.breakdown.is_failed:
                        new_money += reward["add_money"]
                        self._log.append(f"Planet ({contract_id}): +${reward['add_money']}")
                # Pluto (Capot bonus)
                if event.capot and not event.breakdown.is_failed:
                    pluto_reward = self.contract_levels.get("capot", {})
                    if pluto_reward.get("capot_bonus"):
                        new_chips += pluto_reward["capot_bonus"]
                        self._log.append(f"Pluton: +{pluto_reward['capot_bonus']} chips (capot)")
                # Libra (Coinche): +X Mult per coinche level on success
                if (
                    event.coinche_level > 0
                    and event.taker_seat in _NS_TEAM
                    and not event.breakdown.is_failed
                ):
                    libra_reward = self.contract_levels.get("coinche", {})
                    libra_mult: float = libra_reward.get("coinche_multiplier", 0)
                    if libra_mult:
                        libra_bonus: float = libra_mult * event.coinche_level
                        new_mult += libra_bonus
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

        # Update GameState with new values
        return replace(
            state,
            _chips=new_chips,
            _mult=new_mult,
            _bonus_money=new_money,
            _joker_state=joker_state,
        )

    def get_total(self, state: GameState) -> int:
        # Clamp at 0: corrupted jokers (L'Égoïste in particular) can subtract
        # chips per trick won by partner, and with enough partner tricks the
        # running total can go negative, producing a negative final score.
        # Final score should never be negative — clamp at the scoring boundary.
        chips: int = max(0, state._chips)
        mult: float = state._mult
        if mult == float(int(mult)):
            return chips * int(mult)
        return int(chips * mult)

    def get_popup_lines(self, state: GameState) -> list[str]:
        # Match the clamp in get_total(): L'Égoïste can push _chips negative
        # mid-round; the popup line would otherwise read "Chips -12 × Mult …
        # = 0" which looks like a UI bug rather than the intended clamp.
        chips_display = max(0, state._chips)
        return [*self._log, f"Chips {chips_display} × Mult {state._mult:.1f} = {self.get_total(state)}"]

