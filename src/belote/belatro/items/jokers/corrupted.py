from __future__ import annotations

from typing import TYPE_CHECKING, Any

from belote.game import Seat, team_of

from ...engine.event_bus import TrickWonEvent
from ..base import Joker, JokerResult

if TYPE_CHECKING:
    from ...core.run_state import BelAtroRun


class LeTraitre(Joker):
    id = "le_traitre"
    name = "Le Traître"
    description = (
        "Once purchased, reveals itself: partner throws one trick per round. "
        "+2.5 Mult when you (South) win a trick."
    )
    cost = 6
    is_corrupted = True

    def on_purchase(self, run: BelAtroRun) -> None:
        run.partner_throws_trick = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # Seat-themed (South-only): the joker punishes the partner, so the
        # mult only credits the player who reaped the benefit.
        if event.winner == Seat.SOUTH:
            return JokerResult(add_mult=2.5)
        return None


class LeDemon(Joker):
    id = "le_demon"
    name = "Le Démon"
    description = "+3 Mult unconditionally per trick won. Partner personality permanently degrades one tier."
    cost = 8
    is_corrupted = True

    def on_purchase(self, run: BelAtroRun) -> None:
        # Degrade trust by 3, making partner play worse. 4.7.3: idempotency
        # guard — without it, a save/load round-trip or replay-resume tool
        # that re-runs on_purchase on already-owned jokers would compound
        # the cost. Voucher.apply() solved the same problem in 3.9.3.
        if self.id in run._applied_purchase_ids:
            return
        run._applied_purchase_ids.add(self.id)
        run.partner.trust.value = max(0, run.partner.trust.value - 3)

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # "Unconditionally" per the description: fires for any trick won by
        # team NS (matches the team-aware joker cohort like L'Accumulateur).
        # Pre-4.1.0 this gated on Seat.SOUTH only, contradicting the description.
        if team_of(event.winner) == 0:
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
    description = (
        "+4 Mult when you (South) win a trick. "
        "Partner plays optimally for the opponents for 2 tricks."
    )
    cost = 9
    is_corrupted = True

    def on_purchase(self, run: BelAtroRun) -> None:
        # Flag the run so round_driver flips agent_double_active + populates
        # a 2-trick sabotage set every round. Mirrors Le Traître's wiring.
        run.agent_double_joker = True

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        # Seat-themed (South-only): partner is actively sabotaging, so the
        # mult only credits tricks that survived the sabotage.
        if event.winner == Seat.SOUTH:
            return JokerResult(add_mult=4.0)
        return None
