from __future__ import annotations

from belote.game import Seat

from ...engine.event_bus import RoundEndEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LAventurier(Joker):
    id = "l_aventurier"
    name = "L'Aventurier"
    description = "Partner Joker: If partner and player both win ≥3 tricks, gain ×2 Mult."
    cost = 9
    is_partner_joker = True

    def __init__(self) -> None:
        self._south_wins = 0
        self._north_wins = 0

    def on_round_start(self) -> JokerResult | None:
        self._south_wins = 0
        self._north_wins = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            self._south_wins += 1
        elif event.winner == Seat.NORTH:
            self._north_wins += 1
        if self._south_wins >= 3 and self._north_wins >= 3:
            return JokerResult(times_mult=2.0)
        return None


class LeMartyr(Joker):
    id = "le_martyr"
    name = "Le Martyr"
    description = "Partner Joker: If partner wins 0 tricks, you gain ×3 Mult at round end."
    cost = 8
    is_partner_joker = True

    def __init__(self) -> None:
        self._north_wins = 0

    def on_round_start(self) -> JokerResult | None:
        self._north_wins = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            self._north_wins += 1
        return None

    def on_round_end(self, event: RoundEndEvent) -> JokerResult | None:
        if self._north_wins == 0:
            return JokerResult(times_mult=3.0)
        return None


class LeParasite(Joker):
    id = "le_parasite"
    name = "Le Parasite"
    description = "Partner Joker: Every trick your partner wins beyond 2 gives you +$1."
    cost = 6
    is_partner_joker = True

    def __init__(self) -> None:
        self._north_wins = 0

    def on_round_start(self) -> JokerResult | None:
        self._north_wins = 0
        return None

    def on_trick_won(self, event: TrickWonEvent) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            self._north_wins += 1
            if self._north_wins > 2:
                return JokerResult(add_money=1)
        return None
