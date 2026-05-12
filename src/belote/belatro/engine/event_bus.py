"""Round-scoped pub/sub bus for BelAtro joker / unlock / score-accumulator wiring.

**Scope invariant**: an `EventBus` is created once per round in
`round_driver.drive_round`, subscribed to by the round's accumulator and the
process-wide `UnlockTracker`, then dropped when the round ends. Subscribers
do not need to unsubscribe explicitly — the bus instance and all its
subscriber references are released together.

If you ever extend the bus's scope (run-level, session-level), you MUST also
add explicit unsubscribe calls so subscribers don't accumulate across rounds
and double-fire. The `clear()` method exists for that future use.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from belote.deck import Card, Suit
from belote.game import Seat

if TYPE_CHECKING:
    from belote.scoring import ScoringBreakdown

# ── Event types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrickWonEvent:
    winner: Seat
    cards: tuple[Card, ...]
    trick_number: int  # 1-indexed
    is_last: bool
    card_points: int  # raw card pts in this trick
    trump: Suit | None
    leader_seat: Seat = Seat.SOUTH  # who led this trick


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
    breakdown: "ScoringBreakdown"
    # `taker_seat` is None when the round ended on an all-pass (no contract).
    taker_seat: Seat | None
    trump: Suit | None
    capot: bool
    hand_remainder: tuple[Card, ...] = ()
    contract: str = "normal"
    coinche_level: int = 0  # 0=none, 1=coinche, 2=surcoinche


@dataclass(frozen=True)
class BidMadeEvent:
    seat: Seat
    trump: Suit | None  # None = pass
    contract: str  # "normal" | "tout_atout" | "sans_atout" | "coinche" | "surcoinche"
    coinche_level: int = 0  # 0=none, 1=coinche, 2=surcoinche
    # When True, this event is a post-coinche refresh of an already-emitted bid.
    # Consumers should update derived state (HUD, joker_state["contract"]) but
    # MUST NOT re-fire `on_bid` jokers — those already fired for the original
    # bid during the bidding loop. Without this flag, jokers like Le Passeur
    # would double-count or future on_bid-based scoring would silently overpay.
    re_emit: bool = False


# ── Bus ────────────────────────────────────────────────────────────────────

AnyEvent = (
    TrickWonEvent | BeloteAnnouncedEvent | DeclarationScoredEvent | RoundEndEvent | BidMadeEvent
)
Handler = Callable[[AnyEvent], None]


class EventBus:
    """Round-scoped event bus. See module docstring for the lifetime contract."""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: Handler) -> None:
        import contextlib

        with contextlib.suppress(ValueError):
            self._handlers.remove(handler)

    def emit(self, event: AnyEvent) -> None:
        for h in list(self._handlers):
            h(event)

    def clear(self) -> None:
        """Drop every subscriber.

        Today the round-scoped bus is created fresh per round so this is
        unused, but exists for the future where a longer-lived bus might
        share lifetime across rounds (debug overlays, replay recorders, etc).
        Call before re-using a bus across round boundaries.
        """
        self._handlers.clear()
