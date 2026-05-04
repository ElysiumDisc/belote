"""
Entry point for the `belatro` command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..input import KeyReader

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
        register_all_items()
        self.save_manager = SaveManager()
        self.profile = self.save_manager.load_profile()
        self.unlock_tracker = UnlockTracker(self.profile, self.save_manager)
        self.run: BelAtroRun | None = None
        self.reader: KeyReader | None = None

    def start(self, reader: KeyReader) -> None:
        self.reader = reader
        import sys

        from ..ansi import (
            RESET,
            alt_screen_off,
            alt_screen_on,
            clear_screen,
            hide_cursor,
            show_cursor,
        )

        sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
        sys.stdout.flush()
        try:
            menu = BelAtroMainMenu(self.reader, self.profile)
            self.run = menu.run()

            if self.run:
                self.save_manager.save_profile(self.profile)
                self._run_loop()
        except KeyboardInterrupt:
            # Catch exit signals to return to the Belote main menu
            return
        finally:
            sys.stdout.write(alt_screen_off() + show_cursor() + RESET)
            sys.stdout.flush()

    def _run_loop(self) -> None:
        """Main game loop: Blind -> Shop -> Next."""
        if self.run is None:
            return
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
                    print("YOU WON!")
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
                        return self.prompt_card(state)
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
        if self.run.blind_index == 2:
            import random

            from .run.boss import ALL_BOSS_MODIFIERS

            boss_cls = random.choice(ALL_BOSS_MODIFIERS)
            boss = boss_cls()
            BelAtroAnnounce.boss_reveal(boss, self.reader)

        # Boss-specific pre-round setup
        auto_coinche_active = boss is not None and boss.id == "l_avocat"
        divorce_active = boss is not None and boss.id == "le_divorce"

        if boss is not None and boss.id == "le_fantome_partenaire":
            show_north = False  # partner hand hidden for this round

        if auto_coinche_active:
            acc.target_score *= 2  # L'Avocat: target doubles

        if divorce_active:
            _saved_trust = self.run.partner.trust.value
            self.run.partner.trust.value = 0  # Le Divorce: freeze trust at 0

        # B4: Reset round-specific trust flags
        self.run.partner.trust.auto_capot_used = False

        final_state = drive_round(
            bus=bus,
            partner=self.run.partner,
            boss=boss,
            target_score=self.run.target_score,
            ui_callbacks=UICallbacks(self.reader),
            acc=acc,
        )

        if divorce_active:
            self.run.partner.trust.value = _saved_trust  # restore after round

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
                print("[Assurance Capot] Chute pénalité divisée par deux — round survived.")
            if not failure_softened:
                self.run.run_over = True
                print(f"RUN OVER - Failed to meet target {effective_target} (scored {total}).")
            if not divorce_active:
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

            if not divorce_active:
                if total >= self.run.target_score * 1.5:
                    trust.big_margin_win()
                else:
                    trust.blind_beaten()

        # Partner-specific trust events (skipped under Le Divorce)
        if not divorce_active:
            if bd.taker_team == 0 and bd.is_failed:
                trust.chute()
            elif bd.is_capot and bd.taker_team == 0:
                trust.capot_together()


def main() -> None:
    import sys

    from ..ansi import alt_screen_off, alt_screen_on, clear_screen, hide_cursor, show_cursor
    from ..input import KeyReader

    with KeyReader() as reader:
        sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
        sys.stdout.flush()
        try:
            game = BelAtroGame()
            game.start(reader)
        finally:
            sys.stdout.write(alt_screen_off() + show_cursor())
            sys.stdout.flush()


if __name__ == "__main__":
    main()
