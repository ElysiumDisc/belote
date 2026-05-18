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
                # 3.3.0: route the in-game [H] key to the BelAtro history
                # overlay (reading `self.run.history`) for the duration of
                # the run. Cleared in the finally block so the classic
                # Belote menu returns to the default `state.score_history`
                # path on exit.
                from ..ui.prompts import set_history_override
                from .ui.history import show_belatro_history
                run = self.run  # capture for the closure (mypy: narrowed)
                set_history_override(
                    lambda reader: show_belatro_history(reader, run.history)
                )
                self._run_loop()
        except KeyboardInterrupt:
            # Catch exit signals to return to the Belote main menu
            return
        finally:
            from ..ui.prompts import set_history_override
            set_history_override(None)
            # 3.0.0: append a one-line summary of the just-ended run for the
            # player's own analysis. Best-effort; swallowed on failure.
            if self.run is not None:
                from .run_summary import append_summary
                append_summary(self.run, won=self.run.run_won)
                if self._ghost_recorder is not None:
                    label = "won" if self.run.run_won else f"ante{self.run.ante_number}"
                    self._ghost_recorder.save(label=label)

    def _drain_unlock_announcements(self) -> None:
        """Render any queued unlock notices through the TUI banner.

        Replaces the old raw-stdout `print()` notices in UnlockTracker, which
        scrolled and corrupted the alt-screen buffer.
        """
        if self.reader is None:
            self.unlock_tracker.drain_announcements()
            return
        from .ui.announce import BelAtroAnnounce
        for msg in self.unlock_tracker.drain_announcements():
            BelAtroAnnounce.banner(msg, self.reader, hold=1.5)

    def _run_loop(self) -> None:
        """Main game loop: Blind -> Shop -> Next."""
        if self.run is None:
            return
        from .ui.announce import BelAtroAnnounce
        try:
            while not self.run.run_over:
                # 1. Round (Blind)
                self._play_blind()
                self._drain_unlock_announcements()

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
                self._drain_unlock_announcements()
                if self.run.run_won:
                    self.unlock_tracker.notify_run_won()
                    self._drain_unlock_announcements()
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
        # Phase 3.1: roll an Ante theme at the start of each ante (blind 0).
        # Uses the run's seeded RNG so themes are deterministic per seed.
        # The roll runs once per ante; subsequent blinds re-use the same theme.
        if self.run.blind_index == 0:
            from .run.ante_themes import roll_theme
            theme = roll_theme(self.run._get_rng().random())
            self.run.ante_theme = theme.id if theme is not None else None
            if theme is not None:
                theme.on_ante_start(self.run)
        # 3.3.0: snapshots used at end of round to build the [H] history entry.
        history_ante = self.run.ante_number
        history_blind_index = self.run.blind_index
        history_target = self.run.target_score
        money_before = self.run.economy.money
        bus = EventBus()
        self.unlock_tracker.subscribe_to(bus)
        acc = ScoreAccumulator()
        acc.deck_id = self.run.deck_id
        acc.carnet_active = self.run.show_north_hand
        acc.target_score = self.run.target_score
        # `run.contract_levels` is typed as the wider `dict[str, dict[str, Any]]`
        # to avoid an import cycle; the accumulator's TypedDict-typed reads
        # are checked at the consumer side. The cast keeps mypy quiet on the
        # boundary.
        from typing import cast

        from belote.belatro.core.scoring import ContractReward
        acc.contract_levels = cast("dict[str, ContractReward]", self.run.contract_levels)
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
        run = self.run  # captured for UICallbacks closure (see prompt_bid)

        last_display_state: list[GameState | None] = [None]  # mutable cell for closure

        from belote.deck import Card
        from belote.game import GameState, Seat

        class UICallbacks(RoundUICallbacks):
            def __init__(self, reader: KeyReader):
                self.reader = reader

            def _show_overlay(self, state: GameState) -> None:
                # 4.6.3: I/V now toggles BelAtro top HUD visibility (joker pip
                # strip, ante line, chips×mult, trust bar, synergy tooltip).
                # When hidden, the classic HUD's `Trump:` / `Taker:` fields on
                # row 1 are no longer painted over. `invalidate_diff()` is
                # required so `display()` re-paints row 1 from scratch instead
                # of diffing against the cached frame that still believed the
                # joker strip occupied cols 2–25.
                from ..ui.render import display, invalidate_diff
                from .ui.announce import toggle_top_hud

                toggle_top_hud()
                invalidate_diff()
                display(state, show_north_hand=show_north)
                hud.render(acc, state)
                trust_bar.render()

            def prompt_bid(self, state: GameState) -> object:
                from ..ui.prompts import prompt_bid

                # L'Architecte (4.5.0): offer to buy the contract for $10
                # before showing the normal bid UI. We re-check eligibility
                # each time prompt_bid is called (the loop may come around to
                # SOUTH again after a pass) — money has to be high enough at
                # the moment of purchase. `run` is the BelAtroRun captured in
                # the enclosing closure.
                if (
                    run.card_enhancements.get("buy_contract")
                    and run.economy.money >= 10
                    and BelAtroAnnounce.yes_no(
                        "L'Architecte: buy the contract for $10?", self.reader
                    )
                ):
                    chosen = BelAtroAnnounce.buy_contract_picker(self.reader)
                    if chosen is not None:
                        run.economy.money -= 10
                        BelAtroAnnounce.banner(
                            "Contract bought — $10 spent",
                            self.reader,
                            hold=0.8,
                        )
                        return chosen

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

            def prompt_surcoinche(self, state: GameState, coincheur: Seat) -> bool:
                """3.7.1 D3: ask the NS taker whether to surcoinche after EW coinches."""
                prompt = f"{coincheur.name} coinched! Surcoinche back?"
                return BelAtroAnnounce.yes_no(prompt, self.reader)

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
                from .run.boss import ALL_BOSS_MODIFIERS

                # Use the run's seeded RNG, not the module-level random — same
                # determinism fix the 3.2.0 release applied to shop generation
                # and the three RNG-using tarots. Boss assignment was the last
                # unseeded RNG site in the BelAtro round flow.
                #
                # 3.9.3 (Phase 5): in endless mode, suppress immediate boss
                # repeats by rejecting a pick that's in the last-2 window.
                # We cap the reroll attempts so we never loop on a degenerate
                # pool (e.g. tests that monkeypatch a single boss).
                rng = self.run._get_rng()
                recent = self.run._recent_boss_ids
                boss_cls = rng.choice(ALL_BOSS_MODIFIERS)
                if self.run.endless and len(ALL_BOSS_MODIFIERS) > 3:
                    attempts = 0
                    while boss_cls().id in recent and attempts < 8:
                        boss_cls = rng.choice(ALL_BOSS_MODIFIERS)
                        attempts += 1
                boss = boss_cls()
                # Update the recent-boss window (keep last 2).
                recent.append(boss.id)
                if len(recent) > 2:
                    del recent[: len(recent) - 2]
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
        # 4.5.0: LePrêteur reads this at on_round_start to gate its $0/$50
        # branches. Snapshotted PRE-round so the joker's own payout doesn't
        # feed back into its own threshold.
        round_flags["current_money"] = self.run.economy.money
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
        if self.run.agent_double_joker:
            # L'Agent Double joker: partner sabotages two random tricks per round.
            # round_driver picks the tricks + reuses the agent_double AI path.
            round_flags["agent_double_joker_active"] = True
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

        # Phase 2.1: persist Tout Atout streak between rounds.
        streak = final_state._joker_state.get("tout_streak_streak", 0)
        if isinstance(streak, int):
            self.run.card_enhancements["tout_streak_streak"] = streak

        # Phase 2.3: refresh partner_mood for HUD display.
        self.run.partner_mood = trust.mood()

        effective_target = acc.target_score  # doubled for L'Avocat, normal otherwise
        survived_via_insurance = False
        if total < effective_target:
            # Phase 2.1: Capot Insurance halves the chute loss (one-shot).
            if bd.is_failed and self.run.capot_insurance:
                self.run.capot_insurance = False
                survived_via_insurance = True
                # Defer run-over by one blind: the player paid for a safety net.
                # We treat the round as a survived chute (no run-over flag).
                BelAtroAnnounce.banner(
                    "[Assurance Capot] Chute pénalité divisée par deux — round survived.",
                    self.reader,
                    hold=2.0,
                )
            if not survived_via_insurance:
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
            money_before = self.run.economy.money
            payout = self.run.economy.process_round_end(total - self.run.target_score)
            if auto_coinche_active:
                self.run.economy.add_money(payout * 2)  # L'Avocat: triple total payout
            # JokerResult.add_money is signed: positive = credit, negative = debit.
            # Pre-4.6.5 this branch was `> 0`, which silently dropped LePreteur's
            # `-5` cost (and any other negative-add_money joker) while still
            # applying the multiplier — free ×1.2 Mult on every $50+ round.
            if final_state._bonus_money > 0:
                self.run.economy.add_money(final_state._bonus_money)
            elif final_state._bonus_money < 0:
                # Route through spend_money so the Economy negative guard fires
                # if accumulated debit somehow exceeds wallet (caller's bug).
                self.run.economy.spend_money(-final_state._bonus_money)
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

            # Phase 3.1: fire the ante theme's per-blind-won hook (e.g. Tournoi
            # awards bonus money, Café gives +1 trust on big-blind wins).
            theme = self.run.get_ante_theme()
            if theme is not None:
                blind_payout = self.run.economy.money - money_before
                theme.on_blind_won(self.run, self.run.blind_index, blind_payout)

        # Partner-specific trust events (skipped under Le Divorce)
        if not lock_trust:
            if bd.taker_team == 0 and bd.is_failed:
                trust.chute()
            elif bd.is_capot and bd.taker_team == 0:
                trust.capot_together()

        # 3.3.0: append a BelAtro-side history entry (the [H] overlay reads
        # `self.run.history` via the override hook installed in `start()`).
        self._record_history_entry(
            ante=history_ante,
            blind_index=history_blind_index,
            target=history_target,
            boss=boss,
            final_state=final_state,
            bd=bd,
            total=total,
            money_delta=self.run.economy.money - money_before,
            survived_via_insurance=survived_via_insurance,
        )

    def _record_history_entry(
        self,
        *,
        ante: int,
        blind_index: int,
        target: int,
        boss: object,
        final_state: object,
        bd: object,
        total: int,
        money_delta: int,
        survived_via_insurance: bool,
    ) -> None:
        """Build and append one BelAtroHistoryEntry to `self.run.history`.

        Pulled out of `_play_blind` so the long round body stays readable.
        Kept private — callers should never construct entries directly.
        """
        if self.run is None:
            return
        from .ui.history import BelAtroHistoryEntry

        blind_label = ("Small", "Big", "Boss")[blind_index] if 0 <= blind_index <= 2 else "?"
        boss_name = getattr(boss, "name", None) if boss is not None else None

        taker = getattr(final_state, "taker", None)
        if taker is None:
            taker_label = "—"
        else:
            team = "NS" if taker.value % 2 == 0 else "EW"
            taker_label = f"{taker.name[0]} ({team})"

        contract_field = getattr(final_state, "contract", None)
        trump = getattr(final_state, "trump", None)
        if contract_field == "sans_atout":
            contract_str = "SA"
        elif contract_field == "tout_atout":
            contract_str = "TA"
        elif trump is not None and hasattr(trump, "symbol"):
            contract_str = trump.symbol
        else:
            contract_str = "—"

        is_capot = bool(getattr(bd, "is_capot", False))
        taker_team = getattr(bd, "taker_team", None)
        if total >= target and is_capot and taker_team == 0:
            status = "CAPOT"
        elif total >= target:
            status = "WON"
        elif survived_via_insurance:
            status = "SURVIVED"
        else:
            status = "FAILED"

        tricks_ns = int(getattr(bd, "tricks_ns", 0))
        tricks_ew = int(getattr(bd, "tricks_ew", 0))

        # Pull declaration summaries off the breakdown when present. score_round
        # doesn't currently expose them, so this is best-effort and falls back
        # to empty tuples — the renderer treats those as "─".
        decl_ns: tuple[str, ...] = tuple(getattr(bd, "decl_summary_ns", ()) or ())
        decl_ew: tuple[str, ...] = tuple(getattr(bd, "decl_summary_ew", ()) or ())

        self.run.history.append(
            BelAtroHistoryEntry(
                ante=ante,
                blind_label=blind_label,
                target=target,
                boss_name=boss_name,
                taker_label=taker_label,
                contract=contract_str,
                tricks_ns=tricks_ns,
                tricks_ew=tricks_ew,
                score=total,
                status=status,
                money_delta=money_delta,
                decl_summary_ns=decl_ns,
                decl_summary_ew=decl_ew,
            )
        )


def main() -> None:
    import argparse
    import sys

    from .. import __version__
    from ..ansi import RESET, alt_screen_off, alt_screen_on, clear_screen, hide_cursor, show_cursor
    from ..input import KeyReader

    # Mirrors `belote --version` (src/belote/main.py) so both entry points
    # report the same, package-canonical version.
    parser = argparse.ArgumentParser(
        prog="belatro",
        description="BelAtro — Balatro-inspired roguelite mode for Belote",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()

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
