from __future__ import annotations

from typing import TYPE_CHECKING

from belote.game import Seat

from ..engine.event_bus import DeclarationScoredEvent, RoundEndEvent
from .save import Profile, SaveManager

if TYPE_CHECKING:
    from ..engine.event_bus import EventBus


class UnlockTracker:
    """
    Subscribes to the EventBus and evaluates unlock conditions.
    Updates the Profile and saves progress immediately.

    Unlock notifications are queued on ``pending_announcements`` rather than
    printed directly — raw stdout writes corrupt the alt-screen the TUI runs
    in. The host loop drains the queue and renders each entry through the
    BelAtroAnnounce banner.
    """

    def __init__(self, profile: Profile, save_manager: SaveManager) -> None:
        self.profile = profile
        self.save_manager = save_manager
        self.pending_announcements: list[str] = []

    def drain_announcements(self) -> list[str]:
        """Return queued announcements and clear the buffer."""
        out, self.pending_announcements = self.pending_announcements, []
        return out

    def subscribe_to(self, bus: EventBus) -> None:
        bus.subscribe(self.on_event)

    def on_event(self, event: object) -> None:
        dirty = False

        if isinstance(event, RoundEndEvent):
            dirty |= self._handle_round_end(event)
        elif isinstance(event, DeclarationScoredEvent):
            dirty |= self._handle_declaration(event)

        if dirty:
            self.save_manager.save_profile(self.profile)

    def _handle_declaration(self, event: DeclarationScoredEvent) -> bool:
        """3.9.3 Phase 8: unlock Quinte Royale (legendary joker) when NS
        announces a Quinte. Pre-3.9.3 the joker was marked `is_unlockable`
        but had no path to actually unlock, leaving it unreachable in the
        shop pool.
        """
        if (
            event.seat in (Seat.SOUTH, Seat.NORTH)
            and event.declaration_type == "sequence"
            and event.points >= 100
            and self.profile.unlock("quinte_royale")
        ):
            self.pending_announcements.append(
                "UNLOCKED: Quinte Royale (Legendary — announced a Quinte)"
            )
            return True
        return False

    def _handle_round_end(self, event: RoundEndEvent) -> bool:
        dirty = False

        # 1. Update Stats
        if event.capot:
            self.profile.stats["total_capots"] += 1
            dirty = True

            # Unlock L'Exécuteur on first Capot
            if self.profile.unlock("l_executeur"):
                self.pending_announcements.append(
                    "UNLOCKED: L'Exécuteur Joker (Scored a Capot)"
                )

        # Sans Atout win: NS declared it and succeeded
        if (
            event.trump is None
            and event.taker_seat in (Seat.SOUTH, Seat.NORTH)
            and not event.breakdown.is_failed
        ):
            self.profile.stats["sans_atout_wins"] += 1
            dirty = True
            if self.profile.unlock("l_ideologue"):
                self.pending_announcements.append(
                    "UNLOCKED: L'Idéologue Joker (Won a Sans Atout round)"
                )

        # Tout Atout win: NS declared it and succeeded.
        from belote.deck import Suit

        if (
            event.trump == Suit.TOUT_ATOUT
            and event.taker_seat in (Seat.SOUTH, Seat.NORTH)
            and not event.breakdown.is_failed
        ):
            self.profile.stats["tout_atout_wins"] += 1
            dirty = True
            if self.profile.unlock("le_fanatique"):
                self.pending_announcements.append(
                    "UNLOCKED: Le Fanatique Joker (Won a Tout Atout round)"
                )

        return dirty

    def check_ante_unlocks(self, ante_number: int) -> None:
        """Called when advancing to a new Ante."""
        if ante_number >= 6 and self.profile.unlock("la_surcoinche"):
            self.pending_announcements.append(
                "UNLOCKED: La Surcoinche Voucher (Reached Ante 6)"
            )
            self.save_manager.save_profile(self.profile)

    def notify_run_won(self) -> None:
        """Called by the main game loop when a run (8 antes) is completed."""
        self.profile.stats["runs_won"] += 1

        # Unlock Decks on first win
        unlocked_any = False
        unlocked_any |= self.profile.unlock("le_republicain")
        unlocked_any |= self.profile.unlock("l_ermite")

        if unlocked_any:
            self.pending_announcements.append(
                "UNLOCKED: New Starting Decks (Won a Run)"
            )

        self.save_manager.save_profile(self.profile)
