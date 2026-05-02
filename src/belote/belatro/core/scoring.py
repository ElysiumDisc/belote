from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..items.base import Joker, JokerResult

from belote.deck import Rank
from belote.game import Seat

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

    chips: int = 0
    mult: float = 1.0
    bonus_money: int = 0
    deck_id: str = "classique"
    carnet_active: bool = False
    _jokers: list[Joker] = field(default_factory=list)
    _log: list[str] = field(default_factory=list)  # for the score popup UI

    def attach_jokers(self, jokers: list[Joker]) -> None:
        self._jokers = jokers

    def on_event(self, event: object) -> None:
        if isinstance(event, TrickWonEvent):
            # Base chips from card points
            self.chips += event.card_points

            # Le Républicain: +5 chips per 7 or 8 captured by your team
            if self.deck_id == "republicain" and event.winner in _NS_TEAM:
                wilds = sum(1 for c in event.cards if c.rank in (Rank.SEVEN, Rank.EIGHT))
                if wilds:
                    self.chips += wilds * 5
                    self._log.append(f"Républicain: +{wilds * 5} chips ({wilds}× wild)")

            # Le Carnet: +1 Mult when South personally wins a trick
            if self.carnet_active and event.winner == Seat.SOUTH:
                self.mult += 1.0
                self._log.append("Le Carnet: +1 Mult (South won trick)")

            # Fire all Joker triggers
            for joker in self._jokers:
                result = joker.on_trick_won(event)
                if result:
                    self._apply(result, source=joker.name)

        elif isinstance(event, BeloteAnnouncedEvent):
            for joker in self._jokers:
                result = joker.on_belote(event)
                if result:
                    self._apply(result, source=joker.name)

        elif isinstance(event, DeclarationScoredEvent):
            self.chips += event.points
            for joker in self._jokers:
                result = joker.on_declaration(event)
                if result:
                    self._apply(result, source=joker.name)

        elif isinstance(event, RoundEndEvent):
            for joker in self._jokers:
                result = joker.on_round_end(event)
                if result:
                    self._apply(result, source=joker.name)

        elif isinstance(event, BidMadeEvent):
            for joker in self._jokers:
                result = joker.on_bid(event)
                if result:
                    self._apply(result, source=joker.name)

    def _apply(self, result: JokerResult, source: str) -> None:
        if result.add_chips:
            self.chips += result.add_chips
            self._log.append(f"{source}: +{result.add_chips} chips")
        if result.add_mult:
            self.mult += result.add_mult
            self._log.append(f"{source}: +{result.add_mult} Mult")
        if result.times_mult:
            self.mult *= result.times_mult
            self._log.append(f"{source}: ×{result.times_mult} Mult")
        if result.add_money:
            self.bonus_money += result.add_money
            self._log.append(f"{source}: +${result.add_money}")

    @property
    def total(self) -> int:
        return int(self.chips * self.mult)

    @property
    def popup_lines(self) -> list[str]:
        return [*self._log, f"Chips {self.chips} × Mult {self.mult:.1f} = {self.total}"]
