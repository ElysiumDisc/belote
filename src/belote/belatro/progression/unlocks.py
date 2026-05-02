from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.event_bus import RoundEndEvent
from .save import Profile, SaveManager

if TYPE_CHECKING:
    from ..engine.event_bus import EventBus


class UnlockTracker:
    """
    Subscribes to the EventBus and evaluates unlock conditions.
    Updates the Profile and saves progress immediately.
    """

    def __init__(self, profile: Profile, save_manager: SaveManager) -> None:
        self.profile = profile
        self.save_manager = save_manager

    def subscribe_to(self, bus: EventBus) -> None:
        bus.subscribe(self.on_event)

    def on_event(self, event: object) -> None:
        dirty = False

        if isinstance(event, RoundEndEvent):
            dirty |= self._handle_round_end(event)

        # Potentially more event handlers (e.g. for specific trick-based unlocks)

        if dirty:
            self.save_manager.save_profile(self.profile)

    def _handle_round_end(self, event: RoundEndEvent) -> bool:
        dirty = False

        # 1. Update Stats
        if event.capot:
            self.profile.stats["total_capots"] += 1
            dirty = True

            # Unlock L'Exécuteur on first Capot
            if self.profile.unlock("l_executeur"):
                print("\n[!] UNLOCKED: L'Exécuteur Joker (Scored a Capot)")

        if event.trump is None:  # Sans Atout
            self.profile.stats["sans_atout_wins"] += 1
            dirty = True
            if self.profile.unlock("l_ideologue"):
                print("\n[!] UNLOCKED: L'Idéologue Joker (Won a Sans Atout round)")

        # Check for Le Fanatique (Win on Tout Atout) - Simplified condition for now
        # "Win a round on Tout Atout without using a trump in the first 3 tricks"
        # We need more state to track the "without using a trump" part.
        # For now, let's just do "Won a Tout Atout round" as a base.
        if event.trump and event.trump.name == "TOUT":  # Assuming a convention for Tout Atout
            self.profile.stats["tout_atout_wins"] += 1
            dirty = True
            if self.profile.unlock("l_fanatique"):
                print("\n[!] UNLOCKED: Le Fanatique Joker (Won a Tout Atout round)")

        return dirty

    def check_ante_unlocks(self, ante_number: int) -> None:
        """Called when advancing to a new Ante."""
        if ante_number >= 6 and self.profile.unlock("la_surcoinche"):
            print("\n[!] UNLOCKED: La Surcoinche Voucher (Reached Ante 6)")
            self.save_manager.save_profile(self.profile)

    def notify_run_won(self) -> None:
        """Called by the main game loop when a run (8 antes) is completed."""
        self.profile.stats["runs_won"] += 1

        # Unlock Decks on first win
        unlocked_any = False
        unlocked_any |= self.profile.unlock("le_republicain")
        unlocked_any |= self.profile.unlock("l_ermite")

        if unlocked_any:
            print("\n[!] UNLOCKED: New Starting Decks (Won a Run)")

        self.save_manager.save_profile(self.profile)
