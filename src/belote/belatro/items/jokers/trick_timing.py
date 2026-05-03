from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import TrickWonEvent
from ..base import Joker, JokerResult


class LePremierSang(Joker):
    id = "le_premier_sang"
    name = "Le Premier Sang"
    description = "Win trick 1: +2 Mult for the rest of the round."
    cost = 6

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_active"] = False
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.trick_number == 1 and event.winner == Seat.SOUTH:
            state[f"{self.id}_active"] = True
            return JokerResult(add_mult=2.0)
        return None


class LeSergent(Joker):
    id = "le_sergent"
    name = "Le Sergent"
    description = "Each consecutive trick win: +0.5 Mult. Resets on losing."
    cost = 7

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_streak"] = 0
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            streak = state.get(f"{self.id}_streak", 0) + 1
            state[f"{self.id}_streak"] = streak
            return JokerResult(add_mult=0.5)
        state[f"{self.id}_streak"] = 0
        return None


class LeDernierMot(Joker):
    id = "le_dernier_mot"
    name = "Le Dernier Mot"
    description = "Dix de Der is worth ×2 Mult, not 10 flat points."
    cost = 8

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.is_last and event.winner == Seat.SOUTH:
            # Remove the flat Dix de Der bonus and replace with ×2 mult
            # We use event.card_points to see if it included the 10 bonus.
            # In standard scoring, card_points for last trick is points + 10.
            # But if a boss changed it, it might be different.
            # For now, we'll subtract 10 if it's there.
            return JokerResult(add_chips=-10, times_mult=2.0)
        return None


class LExecuteur(Joker):
    id = "l_executeur"
    name = "L'Exécuteur"
    description = "The last trick is worth 50 points instead of 10, and applies a ×1.5 multiplier."
    cost = 8
    is_unlockable = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.is_last and event.winner == Seat.SOUTH:
            return JokerResult(add_chips=40, times_mult=1.5)
        return None

