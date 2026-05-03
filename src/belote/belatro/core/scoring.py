from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..items.base import Joker, JokerResult

from belote.deck import Rank
from belote.game import GameState, Seat

from ..engine.event_bus import (
    BeloteAnnouncedEvent,
    BidMadeEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)

_NS_TEAM = {Seat.SOUTH, Seat.NORTH}


@dataclass
class ScoreAccumulator:
    """
    Accumulates Chips and Mult across one round,
    processing Joker triggers as events arrive.
    """

    deck_id: str = "classique"
    carnet_active: bool = False
    partner_jokers_double: bool = False
    _jokers: list[Joker] = field(default_factory=list)
    _log: list[str] = field(default_factory=list)  # for the score popup UI

    def attach_jokers(self, jokers: list[Joker]) -> None:
        self._jokers = jokers

    def trigger_round_start(self, state: GameState) -> GameState:
        """Initialize joker state at the beginning of a round."""
        self._log.clear()  # FIX: Reset log between rounds
        joker_state = dict(state._joker_state)
        for joker in self._jokers:
            result = joker.on_round_start(joker_state)
            if result:
                # We could apply results here too if needed, but usually round_start
                # just initializes internal joker state like streaks.
                pass
        from dataclasses import replace
        return replace(state, _joker_state=joker_state)

    def update_state(self, state: GameState, event: object) -> GameState:
        """Process an event and return an updated GameState with new score/joker state."""
        new_chips = state._chips
        new_mult = state._mult
        new_money = state._bonus_money
        # Create a shallow copy of the joker state to allow mutation by jokers
        # while keeping the original state immutable for the caller
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

        def _fire_jokers(method_name: str, event_obj: Any) -> None:
            for joker in self._jokers:
                method = getattr(joker, method_name, None)
                if method:
                    result = method(event_obj, joker_state)
                    if result:
                        _apply(result, source=joker.name)
                        # Double trigger for partner jokers if trust is high
                        if self.partner_jokers_double and getattr(joker, "is_partner_joker", False):
                            # FIX: Apply a fresh copy/re-calculated result if possible
                            # For simple results, applying again is fine as long as we don't mutate the result object
                            _apply(result, source=f"{joker.name} (Double)")

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

            # Fire all Joker triggers
            _fire_jokers("on_trick_won", event)

        elif isinstance(event, BeloteAnnouncedEvent):
            _fire_jokers("on_belote", event)

        elif isinstance(event, DeclarationScoredEvent):
            new_chips += event.points
            _fire_jokers("on_declaration", event)

        elif isinstance(event, RoundEndEvent):
            _fire_jokers("on_round_end", event)

        elif isinstance(event, BidMadeEvent):
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
        if state._mult == float(int(state._mult)):
            return state._chips * int(state._mult)
        return int(state._chips * state._mult)

    def get_popup_lines(self, state: GameState) -> list[str]:
        return [*self._log, f"Chips {state._chips} × Mult {state._mult:.1f} = {self.get_total(state)}"]

