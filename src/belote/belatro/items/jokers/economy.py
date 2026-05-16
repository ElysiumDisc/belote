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
        # Re-emit short-circuit: cash payouts must fire once per round even if
        # a future replay/UI layer re-emits RoundEndEvent. Pattern mirrors the
        # `re_emit` gating on BidMadeEvent. 4.1.0.
        if getattr(event, "re_emit", False):
            return None
        # Description: "Earn $1 for every 10 card points you score above the
        # Blind target." That framing presumes NS won the contract — under a
        # chute the points aren't "scored" in the meaningful sense, so the
        # bonus doesn't apply. 3.9.3.
        if event.breakdown.is_failed:
            return None
        # Bonus only makes sense when NS held the contract — defender points
        # under chute are computed differently and don't represent "above
        # target" score.
        if event.taker_seat not in (Seat.SOUTH, Seat.NORTH):
            return None
        points = event.breakdown.taker_total
        # Use a dynamic threshold from state or default to 80
        threshold = state.get("target_score", 80)
        bonus = max(0, (points - threshold) // 10)
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

    def on_belote(
        self, event: BeloteAnnouncedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        # Belote/Rebelote points (20) are only awarded if both cards are played.
        # Gate on the second event (rebelote) so we only subtract points that
        # the player actually earned.
        if event.seat == Seat.SOUTH and event.is_rebelote:
            return JokerResult(add_chips=-20, add_money=5)
        return None
