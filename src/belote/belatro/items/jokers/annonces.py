"""Phase 2.2 — Annonce-driven jokers (Tierce charges, Rebelote mult, Quinte legendary)."""

from __future__ import annotations

from typing import Any

from belote.deck import Rank
from belote.game import Seat, team_of

from ...engine.event_bus import (
    BeloteAnnouncedEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
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
        # Re-emit short-circuit (4.1.0 defensive): if a future replay path
        # re-emits the belote/rebelote event, the ×3 mult must not double.
        if getattr(event, "re_emit", False):
            return None
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
        if (
            event.seat in (Seat.SOUTH, Seat.NORTH)
            and event.declaration_type == "sequence"
            and event.points >= 100
        ):
            # Quinte = 100 pts in classic belote scoring; mark for round-end mult.
            state[f"{self.id}_armed"] = True
        return None

    def on_round_end(
        self, event: RoundEndEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        # Re-emit short-circuit (4.1.0): state.pop() consumes the armed flag,
        # so a re-emit would silently disarm without paying out. Skip entirely.
        if getattr(event, "re_emit", False):
            return None
        if state.pop(f"{self.id}_armed", False) and not event.breakdown.is_failed:
            return JokerResult(times_mult=4.0)
        return None


# ── 4.5.0 Conditional Engines ──────────────────────────────────────────────

_NS_SEATS = (Seat.SOUTH, Seat.NORTH)


class LeCollectionneur(Joker):
    """Rewards holding Annonce cards past trick 1.

    Each declared NS Annonce card that's played in trick 2+ pays +$2 and
    +5 Mult. Reads `_ns_annonce_cards` (a shared frozenset stamped by the
    accumulator's DeclarationScoredEvent branch) and checks membership on
    every later trick.
    """

    id = "le_collectionneur"
    name = "Le Collectionneur"
    description = "Each Annonce card played after trick 1: +$2 and +5 Mult."
    cost = 8
    rarity = Rarity.UNCOMMON

    def on_trick_won(
        self, event: TrickWonEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        # Pay-out is per qualifying card; guard against TrickWonEvent re-emits
        # so a replay can't double-credit. Matches the 4.1.0 convention applied
        # to every other state-mutating on_trick_won handler.
        if getattr(event, "re_emit", False):
            return None
        if event.trick_number == 1 or not event.cards:
            return None
        annonce_cards: frozenset[tuple[str, str]] = state.get(
            "_ns_annonce_cards", frozenset()
        )
        if not annonce_cards:
            return None
        # Count cards in this trick that are from an NS-declared Annonce AND
        # were played BY an NS seat (the annonce cards belong to NS players).
        count = 0
        seat = event.leader_seat
        for card in event.cards:
            if seat in _NS_SEATS and (card.suit.name, card.rank.name) in annonce_cards:
                count += 1
            seat = seat.next_seat()
        if count > 0:
            return JokerResult(add_mult=5.0 * count, add_money=2 * count)
        return None


class LeMathematicien(Joker):
    """Each Annonce whose score is a multiple of 5 → ×2 Mult."""

    id = "le_mathematicien"
    name = "Le Mathématicien"
    description = "Each NS Annonce whose score is a multiple of 5: ×2 Mult."
    cost = 7
    rarity = Rarity.UNCOMMON

    def on_declaration(
        self, event: DeclarationScoredEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if event.seat in _NS_SEATS and event.points > 0 and event.points % 5 == 0:
            return JokerResult(times_mult=2.0)
        return None


class LEclat(Joker):
    """Belote (K or Q of trump) winning a trick → triple chips for that trick."""

    id = "l_eclat"
    name = "L'Éclat"
    description = "Win a trick that contains the trump K or Q: triple that trick's chips."
    cost = 9
    rarity = Rarity.RARE

    def on_trick_won(
        self, event: TrickWonEvent, state: dict[str, Any]
    ) -> JokerResult | None:
        if team_of(event.winner) != 0 or event.trump is None or not event.cards:
            return None
        belote_in_trick = any(
            c.suit == event.trump and c.rank in (Rank.KING, Rank.QUEEN)
            for c in event.cards
        )
        if belote_in_trick:
            # JokerResult has no times_chips field — base chips for this trick
            # (event.card_points) are already added by the accumulator's
            # TrickWonEvent branch, so adding 2× more equals tripling.
            return JokerResult(add_chips=2 * event.card_points)
        return None
