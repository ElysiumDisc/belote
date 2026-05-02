from __future__ import annotations

from belote.game import Seat

from ...engine.event_bus import TrickWonEvent
from ..base import Joker, JokerResult


class LePremierSang(Joker):
    id = "le_premier_sang"
    name = "Le Premier Sang"
    description = "Win trick 1: +2 Mult for the rest of the round."
    cost = 6

    def __init__(self) -> None:
        self._active = False

    def on_round_start(self) -> JokerResult | None:
        self._active = False
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH and event.trick_number == 1:
            self._active = True
            return JokerResult(add_mult=2.0)
        return None


class LeSergent(Joker):
    id = "le_sergent"
    name = "Le Sergent"
    description = "Each consecutive trick win: +0.5 Mult. Resets on losing."
    cost = 7

    def __init__(self) -> None:
        self._streak = 0

    def on_round_start(self) -> JokerResult | None:
        self._streak = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            self._streak += 1
            return JokerResult(add_mult=0.5)
        self._streak = 0
        return None


class LeDernierMot(Joker):
    id = "le_dernier_mot"
    name = "Le Dernier Mot"
    description = "Dix de Der is worth ×2 Mult, not 10 flat points."
    cost = 8

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.is_last and event.winner == Seat.SOUTH:
            # Remove the flat +10 bonus and replace with ×2 mult
            return JokerResult(add_chips=-10, times_mult=2.0)
        return None


class LExecuteur(Joker):
    id = "l_executeur"
    name = "L'Exécuteur"
    description = "The last trick is worth 50 points instead of 10, and applies a ×1.5 multiplier."
    cost = 8
    is_unlockable = True

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.is_last and event.winner == Seat.SOUTH:
            return JokerResult(add_chips=40, times_mult=1.5)
        return None
