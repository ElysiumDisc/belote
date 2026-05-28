from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import DeclarationScoredEvent, TrickWonEvent
from ..base import Joker, JokerResult


class LeMiroir(Joker):
    id = "le_miroir"
    name = "Le Miroir"
    description = "Partner Joker: When your partner wins a trick, you gain +5 chips."
    cost = 6
    is_partner_joker = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if event.winner == Seat.NORTH:
            return JokerResult(add_chips=5)
        return None


class LaSymbiose(Joker):
    id = "la_symbiose"
    name = "La Symbiose"
    description = "Partner Joker: Each time your partner scores a declaration, gain ×1.2 Mult."
    cost = 7
    is_partner_joker = True

    def on_declaration(self, event: DeclarationScoredEvent, state: dict[str, Any]) -> JokerResult | None:
        # Gate on points so Le Mime (declarations_zero) — which emits
        # declarations worth 0 — doesn't grant the multiplier for a
        # declaration that scored nothing. Mirrors LeMathematicien's guard.
        if event.seat == Seat.NORTH and event.points > 0:
            return JokerResult(times_mult=1.2)
        return None


class LeRelais(Joker):
    id = "le_relais"
    name = "Le Relais"
    description = "Partner Joker: If partner wins trick 1, you gain +15 chips this round."
    cost = 7
    is_partner_joker = True

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        state[f"{self.id}_triggered"] = False
        return None

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        if (
            event.trick_number == 1
            and event.winner == Seat.NORTH
            and not state.get(f"{self.id}_triggered", False)
        ):
            state[f"{self.id}_triggered"] = True
            return JokerResult(add_chips=15)
        return None
