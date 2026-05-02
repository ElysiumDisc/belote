from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LeGenereux(Joker):
    id = "le_genereux"
    name = "Le Généreux"
    description = "Partner Joker: Each trick your partner wins gives you +3 chips."
    cost = 5
    is_partner_joker = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            return JokerResult(add_chips=3)
        return None


class LaSentinelleP(Joker):
    id = "la_sentinelle_p"
    name = "La Sentinelle (P)"
    description = "Partner Joker: If partner never leads trump, gain ×1.5 Mult."
    cost = 8
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_trump_led"] = False
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH and event.trump is not None:
            for card in event.cards:
                if card.suit == event.trump:
                    state[f"{self.id}_trump_led"] = True
                    break
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if not state.get(f"{self.id}_trump_led", False):
            return JokerResult(times_mult=1.5)
        return None


class LeCalculateur(Joker):
    id = "le_calculateur"
    name = "Le Calculateur"
    description = "Partner Joker: +0.3 Mult for each trick won by partner this round."
    cost = 7
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_north_wins"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            nwins = state.get(f"{self.id}_north_wins", 0) + 1
            state[f"{self.id}_north_wins"] = nwins
            return JokerResult(add_mult=0.3)
        return None
