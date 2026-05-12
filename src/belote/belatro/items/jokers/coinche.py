"""Phase 2.1 — contract-layer jokers that key off coinche/surcoinche state and
the Tout-Atout contract."""

from __future__ import annotations

from typing import Any

from belote.deck import Suit
from belote.game import Seat

from ...engine.event_bus import RoundEndEvent
from ..base import Joker, JokerResult, Rarity


class CoincheStack(Joker):
    """Pays mult when the round was coinched (or surcoinched) and the taker side won."""

    id = "coinche_stack"
    name = "Pile de Coinches"
    description = "+4 Mult per coinche level if the round was won."
    cost = 7
    rarity = Rarity.COMMON

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.coinche_level <= 0:
            return None
        if event.breakdown.is_failed:
            return None
        if event.taker_seat not in (Seat.SOUTH, Seat.NORTH):
            return None
        return JokerResult(add_mult=4.0 * event.coinche_level)


class ToutStreak(Joker):
    """Increments a streak counter on consecutive Tout Atout wins; Mult ramps with streak.

    The streak resets the moment a Tout Atout round is *failed* or any
    non-Tout-Atout round ends. We don't reset on rounds where everyone passed
    (event.trump=None and event.taker_seat=None) so a defended pass round
    doesn't kill the streak.
    """

    id = "tout_streak"
    name = "Élan Tout-Atout"
    description = "Each consecutive Tout Atout you win adds ×0.5 Mult permanently this run."
    cost = 9
    rarity = Rarity.UNCOMMON

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        streak_key = f"{self.id}_streak"
        streak: int = int(state.get(streak_key, 0))

        is_tout = event.trump == Suit.TOUT_ATOUT
        is_taker_won = (
            event.taker_seat in (Seat.SOUTH, Seat.NORTH)
            and not event.breakdown.is_failed
        )

        if is_tout and is_taker_won:
            streak += 1
            state[streak_key] = streak
            return JokerResult(times_mult=1.0 + 0.5 * streak)
        if is_tout and not is_taker_won:
            # Failed a Tout Atout → reset streak.
            state[streak_key] = 0
        # Non-Tout rounds neither advance nor reset the streak.
        return None
