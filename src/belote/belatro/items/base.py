from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from ..engine.event_bus import (
        BeloteAnnouncedEvent,
        BidMadeEvent,
        DeclarationScoredEvent,
        RoundEndEvent,
        TrickWonEvent,
    )


@dataclass(frozen=True)
class JokerResult:
    add_chips: int = 0
    add_mult: float = 0.0
    times_mult: float = 0.0
    add_money: int = 0


class Joker(ABC):
    id: str
    name: str
    description: str
    cost: int = 7
    is_partner_joker: bool = False
    is_corrupted: bool = False

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_declaration(self, event: DeclarationScoredEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_bid(self, event: BidMadeEvent, state: dict[str, Any]) -> JokerResult | None:
        return None


class Planet(ABC):
    id: str
    name: str
    contract_id: str  # which contract this levels up
    level: int = 0
    cost: int = 4
    suit_symbol: str = "?"
    ascii_art: tuple[str, str, str] = (
        "              ",
        "   (  ?  ?  ) ",
        "   Planet  ♪  ",
    )
    shop_lines: tuple[str, str] = ("              ", "              ")

    @abstractmethod
    def level_up_reward(self) -> dict[str, Any]:
        """Returns a dict of stat bumps to apply to contract."""
        ...


class Tarot(ABC):
    id: str
    name: str
    description: str
    cost: int = 4

    @abstractmethod
    def use(self, run: BelAtroRun, context: object) -> None:
        """Apply the one-shot effect."""
        ...


class Voucher(ABC):
    id: str
    name: str
    description: str
    cost: int = 10
    purchased: bool = False

    @abstractmethod
    def apply(self, run: BelAtroRun) -> None:
        """Apply permanent effect to the run."""
        ...
