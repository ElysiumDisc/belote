"""Event factories shared by the BelAtro unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from belote.deck import Card, Suit
from belote.game import Seat

if TYPE_CHECKING:
    from belote.belatro.engine.event_bus import (
        BeloteAnnouncedEvent,
        BidMadeEvent,
        DeclarationScoredEvent,
        RoundEndEvent,
        TrickWonEvent,
    )


def make_trick_event(
    winner: Seat = Seat.SOUTH,
    trick_number: int = 1,
    is_last: bool = False,
    card_points: int = 0,
    cards: tuple[Card, ...] = (),
    trump: Suit | None = None,
    leader_seat: Seat = Seat.SOUTH,
) -> TrickWonEvent:
    from belote.belatro.engine.event_bus import TrickWonEvent

    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=trump,
        leader_seat=leader_seat,
    )


def make_decl_event(
    seat: Seat = Seat.SOUTH, declaration_type: str = "Tierce", points: int = 20
) -> DeclarationScoredEvent:
    from belote.belatro.engine.event_bus import DeclarationScoredEvent

    return DeclarationScoredEvent(seat=seat, declaration_type=declaration_type, points=points)


def make_round_end_event(
    breakdown: Any = None,
    taker_seat: Seat = Seat.SOUTH,
    trump: Suit | None = None,
    capot: bool = False,
    hand_remainder: tuple[Card, ...] = (),
) -> RoundEndEvent:
    from belote.belatro.engine.event_bus import RoundEndEvent

    return RoundEndEvent(
        breakdown=breakdown,
        taker_seat=taker_seat,
        trump=trump,
        capot=capot,
        hand_remainder=hand_remainder,
    )


def make_bid_event(
    seat: Seat = Seat.SOUTH, trump: Suit | None = None, contract: str = "normal"
) -> BidMadeEvent:
    from belote.belatro.engine.event_bus import BidMadeEvent

    return BidMadeEvent(seat=seat, trump=trump, contract=contract)


def make_belote_event(seat: Seat = Seat.SOUTH, is_rebelote: bool = False) -> BeloteAnnouncedEvent:
    from belote.belatro.engine.event_bus import BeloteAnnouncedEvent

    return BeloteAnnouncedEvent(seat=seat, is_rebelote=is_rebelote)
