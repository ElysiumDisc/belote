from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import BeloteAnnouncedEvent, BidMadeEvent, RoundEndEvent
from ..base import Joker, JokerResult


class LeBanquier(Joker):
    id = "le_banquier"
    name = "Le Banquier"
    description = "Earn $1 for every 10 card points you score above the Blind target."
    cost = 7

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        points = (
            event.breakdown.taker_total
            if event.taker_seat in (Seat.SOUTH, Seat.NORTH)
            else event.breakdown.defender_total
        )
        bonus = max(0, (points - 80) // 10)
        if bonus > 0:
            return JokerResult(add_money=bonus)
        return None


class LePasseur(Joker):
    id = "le_passeur"
    name = "Le Passeur"
    description = "Earn $2 every time your AI partner passes during bidding."
    cost = 5

    def on_bid(self, event: BidMadeEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.seat == Seat.NORTH and event.trump is None:
            return JokerResult(add_money=2)
        return None


class LeNotaire(Joker):
    id = "le_notaire"
    name = "Le Notaire"
    description = "Belote/Rebelote is worth $5 cash instead of 20 flat points."
    cost = 6

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.seat == Seat.SOUTH:
            return JokerResult(add_chips=-20, add_money=5)
        return None
