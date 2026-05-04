from __future__ import annotations

from typing import TYPE_CHECKING, Any

from belote.game import Seat

from ...engine.event_bus import TrickWonEvent
from ..base import Joker, JokerResult

if TYPE_CHECKING:
    from ...core.run_state import BelAtroRun


class LeTraitre(Joker):
    id = "le_traitre"
    name = "Le Traître"
    description = (
        "Once purchased, reveals itself: partner throws one trick per round. Gives +2.5 Mult."
    )
    cost = 6
    is_corrupted = True

    def on_purchase(self, run: BelAtroRun) -> None:
        run.partner_throws_trick = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            return JokerResult(add_mult=2.5)
        return None


class LeDemon(Joker):
    id = "le_demon"
    name = "Le Démon"
    description = "+3 Mult unconditionally. Partner personality permanently degrades one tier."
    cost = 8
    is_corrupted = True

    def on_purchase(self, run: BelAtroRun) -> None:
        # Degrade trust by 3, making partner play worse
        run.partner.trust.value = max(0, run.partner.trust.value - 3)

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            return JokerResult(add_mult=3.0)
        return None


class LEgoiste(Joker):
    id = "le_egoiste"
    name = "L'Égoïste"
    description = "You score ALL card points; partner is irrelevant. Extremely powerful."
    cost = 10
    is_corrupted = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.SOUTH:
            return JokerResult(times_mult=2.0)
        if event.winner == Seat.NORTH:
            # Partner's points are nullified
            return JokerResult(add_chips=-event.card_points)
        return None


class LAgentDouble(Joker):
    id = "lagent_double"
    name = "L'Agent Double"
    description = "+4 Mult. Partner plays optimally for the opponents for 2 tricks."
    cost = 9
    is_corrupted = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_sabotage_remaining"] = 2
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # Count down the sabotage window; no score penalty here since it's a behavioral effect
        remaining = state.get(f"{self.id}_sabotage_remaining", 0)
        if remaining > 0 and event.winner in (Seat.EAST, Seat.WEST):
            state[f"{self.id}_sabotage_remaining"] = remaining - 1
        if event.winner == Seat.SOUTH:
            return JokerResult(add_mult=4.0)
        return None
