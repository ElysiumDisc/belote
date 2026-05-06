from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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


@dataclass
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
    contract_levels: dict[str, Any] = field(default_factory=dict)
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

        from dataclasses import replace
        return replace(state, _joker_state=joker_state, _chips=new_chips, _mult=new_mult)

    def update_state(self, state: GameState, event: object) -> GameState:
        """Process an event and return an updated GameState with new score/joker state."""
        new_chips = state._chips
        new_mult = state._mult
        new_money = state._bonus_money
        # Deep-copy the joker state: a shallow dict() shares mutable values
        # (lists/dicts/sets nested inside) across rounds, which has bitten us
        # before with frozenset/list flags persisting after the round ended.
        import copy

        joker_state = copy.deepcopy(state._joker_state)

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

        def _fire_jokers(method_name: str, event_obj: Any) -> None:
            for joker in self._jokers:
                method = getattr(joker, method_name, None)
                if method:
                    result = method(event_obj, joker_state)
                    if result:
                        _apply(result, source=joker.name)
                        # Phase 2.3: partner-joker tier scaling.
                        # tier 0 (degraded) / 1 (base) → just the baseline apply.
                        # tier 2 (boost) / 3 (strong) → +1 apply (≈ ×2 effect),
                        #                               matches legacy partner_jokers_double at trust ≥ 7.
                        # tier 4 (elite) → +2 applies (≈ ×3 effect).
                        # Legacy `partner_jokers_double` flag still forces +1 apply for
                        # back-compat with tests that set it directly.
                        if getattr(joker, "is_partner_joker", False):
                            tier_extras = (0, 0, 1, 1, 2)[self.partner_tier]
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
                    if reward.get("add_money") and not getattr(event.breakdown, "is_failed", False):
                        new_money += reward["add_money"]
                        self._log.append(f"Planet ({contract_id}): +${reward['add_money']}")
                # Pluto (Capot bonus)
                if event.capot and not getattr(event.breakdown, "is_failed", False):
                    pluto_reward = self.contract_levels.get("capot", {})
                    if pluto_reward.get("capot_bonus"):
                        new_chips += pluto_reward["capot_bonus"]
                        self._log.append(f"Pluton: +{pluto_reward['capot_bonus']} chips (capot)")
            _fire_jokers("on_round_end", event)

        elif isinstance(event, BidMadeEvent):
            # Inject contract type into joker state so jokers can read it
            joker_state["contract"] = event.contract
            _fire_jokers("on_bid", event)

        # Update GameState with new values
        from dataclasses import replace
        return replace(
            state,
            _chips=new_chips,
            _mult=new_mult,
            _bonus_money=new_money,
            _joker_state=joker_state,
        )

    def get_total(self, state: GameState) -> int:
        # Avoid float precision issues for large integers if mult is effectively an int
        chips: int = state._chips
        mult: float = state._mult
        if mult == float(int(mult)):
            return chips * int(mult)
        return int(chips * mult)

    def get_popup_lines(self, state: GameState) -> list[str]:
        return [*self._log, f"Chips {state._chips} × Mult {state._mult:.1f} = {self.get_total(state)}"]

