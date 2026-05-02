from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LAventurier(Joker):
    id = "l_aventurier"
    name = "L'Aventurier"
    description = "Partner Joker: If partner and player both win ≥3 tricks, gain ×2 Mult."
    cost = 9
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_south_wins"] = 0
        state[f"{self.id}_north_wins"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            swins = state.get(f"{self.id}_south_wins", 0) + 1
            state[f"{self.id}_south_wins"] = swins
        elif event.winner == Seat.NORTH:
            nwins = state.get(f"{self.id}_north_wins", 0) + 1
            state[f"{self.id}_north_wins"] = nwins

        if state.get(f"{self.id}_south_wins", 0) >= 3 and state.get(f"{self.id}_north_wins", 0) >= 3:
            return JokerResult(times_mult=2.0)
        return None


class LeMartyr(Joker):
    id = "le_martyr"
    name = "Le Martyr"
    description = "Partner Joker: If partner wins 0 tricks, you gain ×3 Mult at round end."
    cost = 8
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_north_wins"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            nwins = state.get(f"{self.id}_north_wins", 0) + 1
            state[f"{self.id}_north_wins"] = nwins
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if state.get(f"{self.id}_north_wins", 0) == 0:
            return JokerResult(times_mult=3.0)
        return None


class LeParasite(Joker):
    id = "le_parasite"
    name = "Le Parasite"
    description = "Partner Joker: Every trick your partner wins beyond 2 gives you +$1."
    cost = 6
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_north_wins"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            nwins = state.get(f"{self.id}_north_wins", 0) + 1
            state[f"{self.id}_north_wins"] = nwins
            if nwins > 2:
                return JokerResult(add_money=1)
        return None
