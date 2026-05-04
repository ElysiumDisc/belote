"""Phase 2.2 — Annonce-driven jokers (Tierce charges, Rebelote mult, Quinte legendary)."""

from __future__ import annotations

from typing import Any

from belote.game import Seat

from ...engine.event_bus import (
    BeloteAnnouncedEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
)
from ..base import Joker, JokerResult, Rarity

_TIERCE_LIKE = frozenset({"sequence", "Tierce", "Quarte", "Quinte"})


class TierceCharger(Joker):
    """Each Tierce/Quarte/Quinte announced grants a charge in the run state.

    Charges are spent in the shop via the `tierce_forge` voucher.
    The joker emits a tiny chip bonus on each charge so the player feels feedback
    in the round it triggers.
    """

    id = "tierce_charger"
    name = "Forgeron d'Annonces"
    description = "Each sequence (Tierce/Quarte/Quinte) you announce gives +5 Chips and +1 charge."
    cost = 6
    rarity = Rarity.COMMON

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if event.seat not in (Seat.SOUTH, Seat.NORTH):
            return None
        if event.declaration_type not in _TIERCE_LIKE:
            return None
        # The run-level counter lives on BelAtroRun; ScoreAccumulator pipes the
        # increment via state["_pending_tierce_charge"] which _play_blind reads.
        state["_pending_tierce_charge"] = state.get("_pending_tierce_charge", 0) + 1
        return JokerResult(add_chips=5)


class RebeloteEcho(Joker):
    """Pays a fat ×Mult specifically when the rebelote (second half) is played."""

    id = "rebelote_echo"
    name = "Écho de Rebelote"
    description = "When you play your Rebelote (the second half of Belote), ×3 Mult that trick."
    cost = 8
    rarity = Rarity.UNCOMMON

    def on_belote(
        self, event: BeloteAnnouncedEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if event.seat == Seat.SOUTH and event.is_rebelote:
            return JokerResult(times_mult=3.0)
        return None


class QuinteRoyale(Joker):
    """Legendary: a Quinte announcement triggers a massive ×Mult on the round."""

    id = "quinte_royale"
    name = "Quinte Royale"
    description = "Announcing a Quinte (5+ sequence) makes the round score ×4."
    cost = 12
    rarity = Rarity.LEGENDARY
    is_unlockable = True

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if event.seat in (Seat.SOUTH, Seat.NORTH) and event.points >= 100:
            # Quinte = 100 pts in classic belote scoring; mark for round-end mult.
            state[f"{self.id}_armed"] = True
        return None

    def on_round_end(
        self, event: RoundEndEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if state.pop(f"{self.id}_armed", False) and not getattr(
            event.breakdown, "is_failed", False
        ):
            return JokerResult(times_mult=4.0)
        return None
