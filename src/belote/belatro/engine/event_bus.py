from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from belote.deck import Card, Suit
from belote.game import Seat

# ── Event types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrickWonEvent:
    winner: Seat
    cards: tuple[Card, ...]
    trick_number: int  # 1-indexed
    is_last: bool
    card_points: int  # raw card pts in this trick
    trump: Suit | None


@dataclass(frozen=True)
class BeloteAnnouncedEvent:
    seat: Seat
    is_rebelote: bool


@dataclass(frozen=True)
class DeclarationScoredEvent:
    seat: Seat
    declaration_type: str  # "Tierce", "Quarte", "Carre", etc.
    points: int


@dataclass(frozen=True)
class RoundEndEvent:
    breakdown: Any  # ScoringBreakdown from belote.scoring
    taker_seat: Seat
    trump: Suit | None
    capot: bool
    hand_remainder: tuple[Card, ...] = ()


@dataclass(frozen=True)
class BidMadeEvent:
    seat: Seat
    trump: Suit | None  # None = pass
    contract: str  # "normal" | "tout" | "sans" | "coinche" | "surcoinche"


# ── Bus ────────────────────────────────────────────────────────────────────

AnyEvent = (
    TrickWonEvent | BeloteAnnouncedEvent | DeclarationScoredEvent | RoundEndEvent | BidMadeEvent
)
Handler = Callable[[AnyEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: Handler) -> None:
        self._handlers.remove(handler)

    def emit(self, event: AnyEvent) -> None:
        for h in list(self._handlers):
            h(event)
