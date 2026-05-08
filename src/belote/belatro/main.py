"""
Entry point for the `belatro` command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..input import KeyReader
    from .ghost_run import GhostRecorder

from .core.run_state import BelAtroRun
from .core.scoring import ScoreAccumulator
from .engine.event_bus import EventBus
from .engine.round_driver import RoundUICallbacks, drive_round
from .items.registry import register_all_items
from .progression.save import SaveManager
from .progression.unlocks import UnlockTracker
from .run.shop import Shop
from .ui.menu import BelAtroMainMenu
from .ui.shop import ShopScreen


class BelAtroGame:
    def __init__(self) -> None:
        import os

        register_all_items()
        self.save_manager = SaveManager()
        self.profile = self.save_manager.load_profile()
        self.unlock_tracker = UnlockTracker(self.profile, self.save_manager)
        self.run: BelAtroRun | None = None
        self.reader: KeyReader | None = None
        # Opt-in feature flags read once at construction time so toggling the
        # env mid-run has no effect (matches the BELOTE_A11Y pattern).
        self._ghost_enabled = bool(os.environ.get("BELOTE_GHOST"))
        self._ghost_recorder: GhostRecorder | None = None

    def start(self, reader: KeyReader) -> None:
        # Caller owns the alt-screen / cursor state. We just clear and run.
        # The classic-Belote entry point (belote.main) keeps the alt-screen
        # active across menu↔BelAtro transitions; the standalone `belatro`
        # console script wraps this in main() below.
        self.reader = reader
        import sys

        from ..ansi import clear_screen, hide_cursor

        sys.stdout.write(clear_screen() + hide_cursor())
        sys.stdout.flush()
        try:
            menu = BelAtroMainMenu(self.reader, self.profile)
            self.run = menu.run()

            if self.run:
                self.save_manager.save_profile(self.profile)
                if self._ghost_enabled:
                    from .ghost_run import GhostRecorder
                    self._ghost_recorder = GhostRecorder(
                        seed=self.run.seed if self.run.seed is not None else 0,
                        deck_id=self.run.deck_id,
                    )
                self._run_loop()
        except KeyboardInterrupt:
            # Catch exit signals to return to the Belote main menu
            return
        finally:
            # 3.0.0: append a one-line summary of the just-ended run for the
            # player's own analysis. Best-effort; swallowed on failure.
            if self.run is not None:
                from .run_summary import append_summary
                append_summary(self.run, won=self.run.run_won)
                if self._ghost_recorder is not None:
                    label = "won" if self.run.run_won else f"ante{self.run.ante_number}"
                    self._ghost_recorder.save(label=label)

    def _run_loop(self) -> None:
        """Main game loop: Blind -> Shop -> Next."""
        if self.run is None:
            return
        from .ui.announce import BelAtroAnnounce
        try:
            while not self.run.run_over:
                # 1. Round (Blind)
                self._play_blind()

                if self.run.run_over:
                    break

                # 2. Shop
                shop = Shop(self.run, self.profile)
                screen = ShopScreen(shop, self.reader)
                screen.run()
                self.save_manager.save_profile(self.profile)

                # 3. Advance
                self.run.advance_blind()
                self.unlock_tracker.check_ante_unlocks(self.run.ante_number)
                if self.run.run_won:
                    self.unlock_tracker.notify_run_won()
                    if self.reader is not None:
                        BelAtroAnnounce.banner("YOU WON!", self.reader, hold=2.5)
                        # 3.0.0: offer Endless mode after the canonical 8 antes.
                        # Skip the prompt when already in endless to avoid a
                        # double-offer if a future endless-victory state is
                        # added.
                        if not self.run.endless and BelAtroAnnounce.yes_no(
                            "Continue into Endless Mode? (Ante 9+ scales ×2.2)",
                            self.reader,
                        ):
                            self.run.enter_endless()
                            self.save_manager.save_profile(self.profile)
                            continue
                    break
        except KeyboardInterrupt:
            self.run.run_over = True
            return

    def _play_blind(self) -> None:
        """Execute one Belote round for the current blind."""
        if self.run is None or self.reader is None:
            return
        bus = EventBus()
        self.unlock_tracker.subscribe_to(bus)
        acc = ScoreAccumulator()
        acc.deck_id = self.run.deck_id
        acc.carnet_active = self.run.show_north_hand
        acc.target_score = self.run.target_score
        acc.contract_levels = self.run.contract_levels
        acc.permanent_chips = self.run.permanent_chips
        acc.permanent_mult = self.run.permanent_mult
        acc.attach_jokers(self.run.jokers + self.run.partner.jokers)

        # UI Implementation of callbacks
        from .ui.announce import BelAtroAnnounce
        from .ui.hud import BelAtroHUD
        from .ui.trust_bar import TrustBar

        hud = BelAtroHUD(self.run)
        trust_bar = TrustBar(self.run.partner.trust)
        show_north = self.run.show_north_hand or self.run.partner.trust.shares_void_info

        last_display_state: list[GameState | None] = [None]  # mutable cell for closure

        from belote.deck import Card
        from belote.game import GameState, Seat

        class UICallbacks(RoundUICallbacks):
            def __init__(self, reader: KeyReader):
                self.reader = reader

            def _show_overlay(self, state: GameState) -> None:
                from ..ui.render import display

                display(state, show_north_hand=show_north)
                hud.render(acc, state)
                trust_bar.render()
                BelAtroAnnounce.score_popup(acc.get_popup_lines(state), self.reader)
                display(state, show_north_hand=show_north)
                hud.render(acc, state)
                trust_bar.render()

            def prompt_bid(self, state: GameState) -> object:
                from ..ui.prompts import prompt_bid

                while True:
                    res = prompt_bid(state, self.reader)
                    if res == "OVERLAY":
                        self._show_overlay(state)
                        continue
                    if res == "QUIT":
                        raise KeyboardInterrupt
                    if isinstance(res, str):
                        return None
                    return res

            def prompt_card(self, state: GameState) -> tuple[Card, GameState]:
                from ..ui.prompts import prompt_card

                while True:
                    card, new_state = prompt_card(state, self.reader, show_north_hand=show_north)
                    if card == "OVERLAY":
                        self._show_overlay(state)
                        continue
                    if card is None:
                        raise KeyboardInterrupt
                    if card == "UNDO":
                        continue
                    if isinstance(card, str):
                        continue
                    return card, new_state

            def on_card_played(self, state: GameState, seat: Seat, card: Card) -> None:
                from dataclasses import replace as dc_replace

                from ..ui.render import display

                if not state.current_trick and state.completed_tricks:
                    display_state = dc_replace(state, current_trick=state.completed_tricks[-1])
                else:
                    display_state = state
                last_display_state[0] = display_state
                display(display_state, show_north_hand=show_north)
                hud.render(acc, display_state)
                trust_bar.render()

            def on_trick_end(self, state: GameState, winner: Seat, points: int) -> None:
                BelAtroAnnounce.score_popup(acc.get_popup_lines(state), self.reader)

            def on_round_end(self, breakdown: object) -> None:
                pass

        # Check if boss
        boss = None
        # Le Joueur deck (`boss_every_2`) adds an extra boss blind on the Big
        # Blind of even-numbered antes — see decks.py.
        is_boss_blind = self.run.blind_index == 2 or (
            bool(self.run.card_enhancements.get("boss_every_2"))
            and self.run.blind_index == 1
            and self.run.ante_number % 2 == 0
        )
        if is_boss_blind:
            # La Maison-Dieu tarot, when used during the previous shop, sets
            # `disable_next_boss` so the upcoming boss blind is replaced by a
            # plain blind. Consume the flag (one-shot effect).
            if self.run.card_enhancements.pop("disable_next_boss", False):
                pass  # boss stays None; deliberately skip the reveal animation
            else:
                import random

                from .run.boss import ALL_BOSS_MODIFIERS

                boss_cls = random.choice(ALL_BOSS_MODIFIERS)
                boss = boss_cls()
                BelAtroAnnounce.boss_reveal(boss, self.reader)

        # Boss-specific pre-round setup, driven by boss_modifiers flags rather
        # than hardcoded boss.id checks (preserves the architecture that the
        # rest of the engine uses and that tests/belatro/test_phase0_coverage.py
        # pins down).
        boss_flags = boss.flags() if boss is not None else None
        auto_coinche_active = boss_flags is not None and boss_flags.auto_coinche
        lock_trust = boss_flags is not None and boss_flags.lock_trust_zero

        if boss_flags is not None and boss_flags.hide_partner_hand:
            show_north = False  # partner hand hidden for this round

        if auto_coinche_active:
            acc.target_score *= 2  # L'Avocat: target doubles

        if lock_trust:
            _saved_trust = self.run.partner.trust.value
            self.run.partner.trust.value = 0  # Le Divorce / La Trahison: freeze trust at 0

        # B4: Reset round-specific trust flags
        self.run.partner.trust.auto_capot_used = False

        # Surface dead voucher flags + deck mods into the round so scoring/legal_cards
        # can honor them. Empty dict if nothing relevant — round_driver no-ops.
        round_flags: dict[str, object] = dict(self.run.card_enhancements)
        if self.run.tie_breaks_for_taker:
            round_flags["tie_breaks_for_taker"] = True
        if self.run.show_partner_bid_tendency:
            personality = self.run.partner.personality
            round_flags["partner_bid_tendency_text"] = (
                f"Partner ({personality.name}): {personality.description}"
            )
        if self.run.partner_throws_trick:
            # Le Traître joker: partner sabotages one random trick per round.
            # round_driver picks the trick + reuses the agent_double AI path.
            round_flags["traitre_active"] = True
        if self.run.surcoinche_unlocked:
            round_flags["surcoinche_unlocked"] = True

        final_state = drive_round(
            bus=bus,
            partner=self.run.partner,
            boss=boss,
            target_score=self.run.target_score,
            ui_callbacks=UICallbacks(self.reader),
            acc=acc,
            card_enhancements=round_flags,
            recorder=self._ghost_recorder,
        )

        if lock_trust:
            self.run.partner.trust.value = _saved_trust  # restore after round

        # Le Diable tarot is one-round only — consume after the round so the
        # partner doesn't permanently over-cut for the rest of the run.
        self.run.card_enhancements.pop("partner_overcut_round", None)

        # Check win/loss and update trust
        total = acc.get_total(final_state)
        from belote.scoring import score_round
        bd = score_round(final_state)
        trust = self.run.partner.trust

        # Phase 2.2: drain pending Tierce charges into the run state.
        pending = final_state._joker_state.get("_pending_tierce_charge", 0)
        if isinstance(pending, int) and pending > 0:
            self.run.tierce_charges += pending

        # Phase 2.3: refresh partner_mood for HUD display.
        self.run.partner_mood = trust.mood()

        effective_target = acc.target_score  # doubled for L'Avocat, normal otherwise
        if total < effective_target:
            # Phase 2.1: Capot Insurance halves the chute loss (one-shot).
            failure_softened = False
            if bd.is_failed and self.run.capot_insurance:
                self.run.capot_insurance = False
                failure_softened = True
                # Defer run-over by one blind: the player paid for a safety net.
                # We treat the round as a survived chute (no run-over flag).
                BelAtroAnnounce.banner(
                    "[Assurance Capot] Chute pénalité divisée par deux — round survived.",
                    self.reader,
                    hold=2.0,
                )
            if not failure_softened:
                self.run.run_over = True
                BelAtroAnnounce.banner(
                    f"RUN OVER — Failed to meet target {effective_target} (scored {total}).",
                    self.reader,
                    color="red",
                    hold=2.5,
                )
            if not lock_trust:
                trust.blind_failed()
        else:
            payout = self.run.economy.process_round_end(total - self.run.target_score)
            if auto_coinche_active:
                self.run.economy.add_money(payout * 2)  # L'Avocat: triple total payout
            if final_state._bonus_money > 0:
                self.run.economy.add_money(final_state._bonus_money)
            if final_state._joker_state.get("puriste_triggered"):
                extra = max(0, (total - self.run.target_score) // 10)
                self.run.economy.add_money(extra)  # Le Puriste: double base payout

            # L'Aristocrate deck: +$1 per Ace captured by NS team this round.
            if self.run.gold_seal_aces:
                from belote.deck import Rank
                from belote.game import team_of, trick_winner_seat
                aces_won = 0
                trump = final_state.trump
                se_trump = final_state.boss_modifiers.seven_eight_trump
                is_sa = final_state.contract == "sans_atout"
                for trick in final_state.completed_tricks:
                    w = trick_winner_seat(trick, trump, se_trump, is_sa)
                    if w is not None and team_of(w) == 0:
                        aces_won += sum(1 for tc in trick if tc.card.rank == Rank.ACE)
                if aces_won > 0:
                    self.run.economy.add_money(aces_won)

            if not lock_trust:
                if total >= self.run.target_score * 1.5:
                    trust.big_margin_win()
                else:
                    trust.blind_beaten()

        # Partner-specific trust events (skipped under Le Divorce)
        if not lock_trust:
            if bd.taker_team == 0 and bd.is_failed:
                trust.chute()
            elif bd.is_capot and bd.taker_team == 0:
                trust.capot_together()


def main() -> None:
    import sys

    from ..ansi import RESET, alt_screen_off, alt_screen_on, clear_screen, hide_cursor, show_cursor
    from ..input import KeyReader

    with KeyReader() as reader:
        sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
        sys.stdout.flush()
        try:
            game = BelAtroGame()
            game.start(reader)
        finally:
            sys.stdout.write(alt_screen_off() + show_cursor() + RESET)
            sys.stdout.flush()


if __name__ == "__main__":
    main()
