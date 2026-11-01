from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from belote.deck import Rank
from belote.game import Seat

from ..engine.event_bus import DeclarationScoredEvent, RoundEndEvent, TrickWonEvent
from .save import Profile, SaveManager

if TYPE_CHECKING:
    from ..engine.event_bus import EventBus

_log = logging.getLogger(__name__)


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
        """Dispatch bus events to unlock handlers.

        Handled event types (4.6.5):
          - `RoundEndEvent` → Capot / chute / Tout Atout / total-money unlocks
            via `_handle_round_end`.
          - `DeclarationScoredEvent` → Quinte Royale unlock via
            `_handle_declaration` (3.9.3).

        Other bus events (BidMadeEvent, TrickWonEvent, BeloteAnnouncedEvent)
        are intentionally no-op; subscribe a new branch here when a future
        unlock keys off them.
        """
        dirty = False

        if isinstance(event, RoundEndEvent):
            dirty |= self._handle_round_end(event)
        elif isinstance(event, DeclarationScoredEvent):
            dirty |= self._handle_declaration(event)
        elif isinstance(event, TrickWonEvent):
            dirty |= self._handle_trick(event)
        else:
            # 4.8.2 (L2): silent no-op was the contract pre-4.8.2, but it
            # masked the case where a new unlock keys off a previously-
            # unhandled event type (e.g. TrickWonEvent). A debug-level log
            # lets future maintainers see misses via `BELOTE_LOG_LEVEL=DEBUG`
            # without breaking prod (default log level is WARNING).
            _log.debug("UnlockTracker: unhandled event type %s", type(event).__name__)

        if dirty:
            self.save_manager.save_profile(self.profile)

    def _handle_trick(self, event: TrickWonEvent) -> bool:
        """4.11.0 secret: Le Petit Poucet unlocks when South takes the last
        trick (Dix de Der) with a 7 — the smallest card having the last word.
        """
        if not event.is_last or event.winner != Seat.SOUTH:
            return False
        card = event.winning_card
        if card is None or card.rank != Rank.SEVEN:
            return False
        if self.profile.unlock("le_petit_poucet"):
            self.pending_announcements.append(
                "SECRET UNLOCKED: Le Petit Poucet Joker (took Dix de Der with a 7)"
            )
            return True
        return False

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

        # 1. Update Stats — only the player's team's capots count (`capot`
        # is also True when EW capots NS).
        if event.ns_capot:
            self.profile.stats["total_capots"] += 1
            dirty = True

            # Unlock L'Exécuteur on first Capot
            if self.profile.unlock("l_executeur"):
                self.pending_announcements.append("UNLOCKED: L'Exécuteur Joker (Scored a Capot)")

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
            self.pending_announcements.append("UNLOCKED: La Surcoinche Voucher (Reached Ante 6)")
            self.save_manager.save_profile(self.profile)

    def notify_boss_defeated(self) -> None:
        """4.11.0: a Boss Blind was beaten in a normal run. Counts toward the
        Le Complice deck unlock."""
        from ..run.decks import COMPLICE_BOSSES_REQUIRED, COMPLICE_UNLOCK_ID

        self.profile.stats["bosses_defeated"] = self.profile.stats.get("bosses_defeated", 0) + 1
        if self.profile.stats["bosses_defeated"] >= COMPLICE_BOSSES_REQUIRED and (
            self.profile.unlock(COMPLICE_UNLOCK_ID)
        ):
            self.pending_announcements.append(
                f"UNLOCKED: Le Complice Deck (defeated {COMPLICE_BOSSES_REQUIRED} Boss Blinds)"
            )
        self.save_manager.save_profile(self.profile)

    def notify_run_won(self) -> None:
        """Called by the main game loop when a run (8 antes) is completed."""
        self.profile.stats["runs_won"] += 1
        # 4.11.0: the first win used to "unlock" Le Républicain and L'Ermite
        # and announce new decks — but those decks were never locked, so the
        # banner promised nothing. Removed; Le Complice is the locked deck.
        self.save_manager.save_profile(self.profile)
