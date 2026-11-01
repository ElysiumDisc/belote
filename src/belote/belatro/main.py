"""
Entry point for the `belatro` command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .core.state import BelatroState, joker_flag

if TYPE_CHECKING:
    from belote.deck import Card
    from belote.game import BidValue, GameState, Seat
    from belote.scoring import ScoringBreakdown

    from ..input import KeyReader
    from .ghost_run import GhostRecorder
    from .progression.save import Profile
    from .run.boss import BossModifier
    from .ui.hud import BelAtroHUD
    from .ui.trust_bar import TrustBar

from ..input import Key
from ..ui.fit_guard import FitAbortedError
from ..ui.prompts import ExtensionKey, register_extension_keys, unregister_extension_keys
from ..ui.render import set_bid_hint_provider, set_overlay_provider
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

# Keys BelAtro takes over from the core prompts while a run is active:
# I toggles the top HUD overlay, V opens the inventory.
_RUN_KEYS = (Key.OVERLAY, Key.INVENTORY)


def _legal_bids(state: BelatroState) -> list[BidValue]:
    """Non-pass bids legal for SOUTH in the current bidding round."""
    from belote.game import legal_bids

    return [b for b in legal_bids(state) if b is not None]


def toast_cosmetic_unlocks(reader: KeyReader | None) -> None:
    """4.11.0: toast card backs / frames earned in BelAtro (L'Insider, the
    Daily calendar back) right away instead of at the next classic round."""
    if reader is None:
        return
    from ..cosmetics import unlock_toasts
    from ..ui.announce import achievement_toast

    for toast in unlock_toasts():
        achievement_toast(toast, reader)


def _overlay_rows() -> tuple[int, int]:
    """Rows the in-round HUD paints over the classic table (top, bottom),
    for the core's vertical budget (4.11.0). The bottom tally ends at
    term_h - 1, so it keeps the last row free too: +1. Hidden HUD (I) → 0."""
    from .ui.announce import is_top_hud_visible
    from .ui.hud import BOTTOM_OVERLAY_ROWS, TOP_OVERLAY_ROWS

    if not is_top_hud_visible():
        return (0, 0)
    return (TOP_OVERLAY_ROWS, BOTTOM_OVERLAY_ROWS + 1)


def _partner_bid_hint(state: GameState) -> str | None:
    """Bid-selector hint: the partner's tendency (Le Carnet de Bord voucher,
    stamped into joker_state by `_round_flags`)."""
    hint = joker_flag(state, "partner_bid_tendency_text")
    return hint if isinstance(hint, str) and hint else None


def _aces_won_by_team(state: BelatroState, team: int) -> int:
    """Aces captured by `team` across the round's completed tricks.

    Resolves winners via `compute_trick_winners` so La Rupture flips and
    L'Anarchie's per-trick trumps are honored -- the same resolution
    `score_round` uses. Re-deriving with raw `trick_winner_seat` and the
    final trump credited aces to the wrong team under those bosses.
    """
    from belote.deck import Contract, Rank
    from belote.game import compute_trick_winners, team_of

    is_sa = state.contract == Contract.SANS_ATOUT
    winners = compute_trick_winners(state, state.trump, is_sa)
    return sum(
        sum(1 for tc in trick if tc.card.rank == Rank.ACE)
        for trick, w in zip(state.completed_tricks, winners, strict=True)
        if w is not None and team_of(w) == team
    )


class UICallbacks(RoundUICallbacks):
    """BelAtro round-UI callbacks. Wraps the classic ``prompt_bid`` /
    ``prompt_card`` flow with overlay handling, BelAtro HUD + trust-bar
    repaint, L'Architecte buy-contract, Dix de Der Heist prompt, and
    surcoinche prompt.

    Extracted from ``BelAtroGame._play_blind`` for readability — the
    eight dependencies were previously captured via closure cells. The
    interfaces (RoundUICallbacks methods) are unchanged.
    """

    def __init__(
        self,
        reader: KeyReader,
        run: BelAtroRun,
        profile: Profile,
        save_manager: SaveManager,
        acc: ScoreAccumulator,
        hud: BelAtroHUD,
        trust_bar: TrustBar,
        show_north: bool,
    ) -> None:
        self.reader = reader
        self.run = run
        self.profile = profile
        self.save_manager = save_manager
        self.acc = acc
        self.hud = hud
        self.trust_bar = trust_bar
        self.show_north = show_north

    def _show_overlay(self, state: BelatroState) -> None:
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
        display(state, show_north_hand=self.show_north)
        self.hud.render(self.acc, state)
        self.trust_bar.render(state)

    def prompt_bid(self, state: BelatroState) -> BidValue:
        from ..game import SANS_ATOUT_BID
        from ..ui.prompts import prompt_bid
        from .ui.announce import BelAtroAnnounce

        # L'Architecte (4.5.0): offer to buy the contract for $10
        # before showing the normal bid UI. Re-checked each call (the
        # loop may come around to SOUTH again after a pass) — money has
        # to be high enough at the moment of purchase.
        if (
            self.run.card_enhancements.get("buy_contract")
            and self.run.economy.money >= 10
            and BelAtroAnnounce.yes_no("L'Architecte: buy the contract for $10?", self.reader)
        ):
            # Offer only bids legal this bidding round — round 1: the up-card
            # suit only; round 2: any other suit, or TA/SA. Money is taken only
            # once the pick is known legal: an illegal pick used to be paid for
            # and then crash in place_bid (IllegalMoveError).
            legal = _legal_bids(state)
            chosen = BelAtroAnnounce.buy_contract_picker(self.reader, legal)
            bought = next((b for b in legal if b == chosen), None)
            if bought is not None:
                self.run.economy.money -= 10
                BelAtroAnnounce.banner(
                    "Contract bought — $10 spent",
                    self.reader,
                    hold=0.8,
                )
                return bought

        while True:
            res = prompt_bid(state, self.reader)
            if res == ExtensionKey(Key.OVERLAY):
                self._show_overlay(state)
                continue
            if res == "QUIT":
                raise KeyboardInterrupt
            # Sans Atout is the plain string "sans_atout": match it before the
            # generic str filter for UI sentinels ("UNDO" → pass), which
            # pre-4.10.0 silently turned an SA bid into a pass.
            if res == SANS_ATOUT_BID:
                return SANS_ATOUT_BID
            if isinstance(res, (str, ExtensionKey)):
                return None
            return res

    def prompt_card(self, state: BelatroState) -> tuple[Card, BelatroState]:
        from ..ui.prompts import prompt_card

        # 4.7.0 follow-up: hook the BelAtro HUD + trust bar into the
        # classic prompt_card loop so the persistent slot-machine tally
        # readout (gated on `_top_hud_visible`) repaints after every
        # `display()` call. Without this hook, between-tricks the player
        # sees the felt mat but no readout — the HUD is only refreshed
        # by `on_card_played` (post-play) and `_show_overlay` (I-toggle).
        def _hud_after_display(s: BelatroState) -> None:
            self.hud.render(self.acc, s)
            self.trust_bar.render(s)

        while True:
            card, new_state = prompt_card(
                state,
                self.reader,
                show_north_hand=self.show_north,
                after_display=_hud_after_display,
            )
            if card == ExtensionKey(Key.OVERLAY):
                self._show_overlay(state)
                continue
            if card == ExtensionKey(Key.INVENTORY):
                # 4.7.0: V key — open the InventoryOverlay (read-only
                # view of jokers/vouchers/consumables/permanent
                # bonuses/contract levels). Wraps with invalidate_diff()
                # then re-renders so the player returns to a clean
                # card-selection prompt.
                self._show_inventory(state)
                continue
            if card is None:
                raise KeyboardInterrupt
            if card == "UNDO":
                continue
            if isinstance(card, (str, ExtensionKey)):
                continue
            return card, new_state

    def _show_inventory(self, state: BelatroState) -> None:
        """Open the V-key inventory overlay and repaint on exit."""
        from belote.ui.render import display, invalidate_diff

        from .ui.inventory import InventoryOverlay

        InventoryOverlay(self.run, self.reader).open()
        invalidate_diff()
        display(state, show_north_hand=self.show_north)
        self.hud.render(self.acc, state)
        self.trust_bar.render(state)

    def on_card_played(self, state: BelatroState, seat: Seat, card: Card) -> None:
        from dataclasses import replace as dc_replace

        from ..ui.render import display

        if not state.current_trick and state.completed_tricks:
            display_state = dc_replace(state, current_trick=state.completed_tricks[-1])
        else:
            display_state = state
        display(display_state, show_north_hand=self.show_north)
        self.hud.render(self.acc, display_state)
        self.trust_bar.render(display_state)

    def on_trick_end(self, state: BelatroState, winner: Seat, points: int) -> None:
        # 4.7.0: animated odometer-style tally replaces the static
        # multi-line popup. The popup helper is kept defined for one
        # release in case a future BelAtro overlay needs the per-trick
        # log breakdown.
        from .ui.announce import BelAtroAnnounce

        BelAtroAnnounce.slot_machine_tally(self.acc, state, self.reader, points=points)

    def on_round_end(self, breakdown: object) -> None:
        pass

    def on_redeal(self, state: BelatroState) -> None:
        from ..ui.render import invalidate_diff
        from .ui.announce import BelAtroAnnounce

        BelAtroAnnounce.banner("Everyone passed — redeal", self.reader, hold=1.0)
        invalidate_diff()  # banner bypassed the diff renderer; repaint fully

    def prompt_coinche(self, state: BelatroState, taker: Seat) -> bool:
        """Le Tournoi ante theme: "Coinche always offered".

        Outside Le Tournoi BelAtro keeps its usual flow (no player coinche
        prompt; the partner AI may still coinche on its own).
        """
        if not self.run.card_enhancements.get("always_offer_coinche"):
            return False
        from .ui.announce import BelAtroAnnounce

        return BelAtroAnnounce.yes_no(f"{taker.name} took the bid. Coinche (x2)?", self.reader)

    def prompt_surcoinche(self, state: BelatroState, coincheur: Seat) -> bool:
        """3.7.1 D3: ask the NS taker whether to surcoinche after EW coinches."""
        from .ui.announce import BelAtroAnnounce

        prompt = f"{coincheur.name} coinched! Surcoinche back?"
        return BelAtroAnnounce.yes_no(prompt, self.reader)

    def prompt_heist(self, state: BelatroState) -> bool:
        """4.7.0: Dix de Der Heist declaration prompt.

        Two gates collapse the prompt when the heist has no value:
          - ``state.taker == Seat.SOUTH``: only the player declares; AI
            seats never get the prompt. The engine already gates on this
            too — belt-and-suspenders here so a future direct caller
            can't slip past.
          - ``self.acc.interest_rate > 0``: with rate=0 the multiplier
            is 1× (no reward), so declaring is pure downside. Default
            Economy.interest_rate is 0 — La Voûte voucher or one of the
            rate-bumping tarots must be purchased to enable.

        Discoverability hint (4.7.0): when the player takes a contract
        without La Voûte, show a one-time explainer banner.
        ``self.profile.seen_heist_hint`` is flipped True and persisted,
        so the hint never shows again for this profile.
        """
        from belote.game import Seat as _Seat

        from .ui.announce import BelAtroAnnounce

        if state.taker != _Seat.SOUTH:
            return False
        if self.acc.interest_rate <= 0:
            if not self.profile.seen_heist_hint:
                BelAtroAnnounce.banner(
                    "Tip: buy the La Voûte voucher in the shop to unlock "
                    "the Dix de Der Heist (×2+ Mult on trick 8).",
                    self.reader,
                    hold=2.5,
                )
                self.profile.seen_heist_hint = True
                self.save_manager.save_profile(self.profile)
            return False
        multiplier = 1 + self.acc.interest_rate
        declared = BelAtroAnnounce.yes_no(
            f"DIX DE DER HEIST — Win trick 8 for ×{multiplier} Mult, "
            "or lose trick 8 and forfeit tricks 1-7 chips. Declare?",
            self.reader,
        )
        if declared:
            BelAtroAnnounce.banner(
                "DIX DE DER HEIST DECLARED — all in on trick 8",
                self.reader,
                hold=1.5,
            )
        return declared


class BelAtroGame:
    def __init__(self) -> None:

        register_all_items()
        self.save_manager = SaveManager()
        self.profile = self.save_manager.load_profile()
        self.unlock_tracker = UnlockTracker(self.profile, self.save_manager)
        self.run: BelAtroRun | None = None
        self.reader: KeyReader | None = None
        # Opt-in feature flags read once at construction time so toggling the
        # env mid-run has no effect (matches the BELOTE_A11Y pattern).
        from .. import settings
        from .integration import GHOST_TOGGLE

        self._ghost_enabled = settings.current().extra_on(GHOST_TOGGLE.key)
        self._ghost_recorder: GhostRecorder | None = None

    def start(self, reader: KeyReader, run: BelAtroRun | None = None) -> None:
        """Run BelAtro from its own menu, or play the given preset `run`
        (e.g. a Daily Challenge) directly."""
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
            if run is not None:
                self.run = run
            else:
                self.run = BelAtroMainMenu(self.reader, self.profile).run()

            if self.run:
                self.save_manager.save_profile(self.profile)
                if self._ghost_enabled:
                    from .ghost_run import GhostRecorder

                    # BelAtroRun picks a seed at creation when none is given,
                    # so this is the real seed the run's RNG uses.
                    self._ghost_recorder = GhostRecorder(
                        seed=self.run.seed if self.run.seed is not None else 0,
                        deck_id=self.run.deck_id,
                    )
                    self._ghost_recorder.note_run_start(self.run)
                    # Shop + consumable events report through the run.
                    self.run.recorder = self._ghost_recorder
                # 3.3.0: route the in-game [H] key to the BelAtro history
                # overlay (reading `self.run.history`) for the duration of
                # the run. Cleared in the finally block so the classic
                # Belote menu returns to the default `state.score_history`
                # path on exit.
                from ..ui.prompts import set_history_override
                from .ui.history import show_belatro_history

                run = self.run  # capture for the closure (mypy: narrowed)
                set_history_override(lambda reader: show_belatro_history(reader, run.history))
                set_bid_hint_provider(_partner_bid_hint)
                set_overlay_provider(_overlay_rows)
                register_extension_keys(*_RUN_KEYS)
                self._run_loop()
        except (KeyboardInterrupt, FitAbortedError):
            # Catch exit signals (incl. Q on a "terminal too small" screen
            # raised by require_minimum) to return to the Belote main menu.
            return
        finally:
            from ..ui.prompts import set_history_override

            set_history_override(None)
            set_bid_hint_provider(None)
            set_overlay_provider(None)
            unregister_extension_keys(*_RUN_KEYS)
            # 3.0.0: append a one-line summary of the just-ended run for the
            # player's own analysis. Best-effort; swallowed on failure.
            if self.run is not None:
                from .run_summary import append_summary

                # enter_endless() clears run_won to re-open the run, but being
                # in endless at all means ante 8 was beaten — still a victory.
                won = self.run.run_won or self.run.endless
                append_summary(self.run, won=won)
                if self._ghost_recorder is not None and self._ghost_recorder.rounds_played:
                    # Winning AND losing runs are kept (the toggle gates both);
                    # a run quit before its first blind has nothing to watch.
                    label = "won" if won else f"ante{self.run.ante_number}"
                    self._ghost_recorder.note_run_end(self.run, won=won)
                    self._ghost_recorder.save(label=label)
                toast_cosmetic_unlocks(self.reader)

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

    def _reconcile_bonus_money(self, bonus_money: int) -> None:
        """Apply a round's signed joker money to the wallet.

        ``final_state._bonus_money`` accumulates ``JokerResult.add_money`` over
        the round (positive = credit, negative = debit such as LePreteur's -$5
        skim). Positive amounts credit; negative amounts route through
        ``spend_money`` (which no-ops if the wallet can't cover it) so the
        Economy's non-negative guard on ``add_money`` is respected.
        """
        if self.run is None:
            return
        if bonus_money > 0:
            self.run.economy.add_money(bonus_money)
        elif bonus_money < 0:
            # 4.11.0: a debit larger than the wallet takes what is there
            # (Le Contre-Attaquant's steals) instead of silently no-oping.
            self.run.economy.spend_money(min(-bonus_money, self.run.economy.money))

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
                from .progression.save import Profile

                pool = Profile() if self.run.daily else None  # daily: starter pool
                shop = Shop(self.run, self.profile, pool=pool)
                assert self.reader is not None  # set by start()
                screen = ShopScreen(shop, self.reader)
                screen.run()
                self.save_manager.save_profile(self.profile)

                # 3. Advance
                self.run.advance_blind()
                # Boss Rush runs (4.11.0) don't count toward run milestones.
                if not self.run.challenge:
                    self.unlock_tracker.check_ante_unlocks(self.run.ante_number)
                self._drain_unlock_announcements()
                if self.run.run_won:
                    if not self.run.challenge:
                        self.unlock_tracker.notify_run_won()
                    self._drain_unlock_announcements()
                    if self.reader is not None:
                        BelAtroAnnounce.banner("YOU WON!", self.reader, hold=2.5)
                        # 3.0.0: offer Endless mode after the canonical 8 antes.
                        # Skip the prompt when already in endless to avoid a
                        # double-offer if a future endless-victory state is
                        # added.
                        if (
                            not self.run.endless
                            and not self.run.daily
                            and not self.run.challenge
                            and BelAtroAnnounce.yes_no(
                                "Continue into Endless Mode? (Ante 9+ scales ×2.2)",
                                self.reader,
                            )
                        ):
                            self.run.enter_endless()
                            self.save_manager.save_profile(self.profile)
                            continue
                    break
        except (KeyboardInterrupt, FitAbortedError):
            self.run.run_over = True
            return

    def _play_blind(self) -> None:
        """Execute one Belote round for the current blind.

        4.10.0: split into phase helpers (setup → boss → round → settlement);
        run-RNG draw order is unchanged (theme roll → boss pick → deal seed).
        """
        run, reader = self.run, self.reader
        if run is None or reader is None:
            return
        if run.blind_index == 0:
            self._roll_ante_theme(run)
        # 3.3.0: snapshots used at end of round to build the [H] history entry.
        history_ante = run.ante_number
        history_blind_index = run.blind_index
        money_before = run.economy.money
        bus = EventBus()
        self.unlock_tracker.subscribe_to(bus)
        acc = self._build_accumulator(run)

        from .ui.announce import reset_tally_state
        from .ui.hud import BelAtroHUD
        from .ui.trust_bar import TrustBar

        hud = BelAtroHUD(run)
        trust_bar = TrustBar(run.partner.trust)
        # 4.7.0: clear the slot-machine tally cache so this round's animation
        # starts from 0 rather than the previous round's final total.
        reset_tally_state()
        # Full partner hand only with Le Carnet. Trust 3+ ("Void Info") shows
        # North's void suits on the trust bar instead — pre-4.9.7 it revealed
        # the whole hand from the starting trust of 5, making Le Carnet moot.
        show_north = run.show_north_hand

        boss = self._pick_boss(run, reader)
        # Boss-specific pre-round setup, driven by variants flags rather
        # than hardcoded boss.id checks (pinned by test_phase0_coverage.py).
        boss_flags = boss.flags() if boss is not None else None
        auto_coinche_active = boss_flags is not None and boss_flags.auto_coinche
        lock_trust = boss_flags is not None and boss_flags.lock_trust_zero
        if boss_flags is not None and boss_flags.hide_partner_hand:
            show_north = False  # partner hand hidden for this round
            trust_bar.show_voids = False  # ...and so are its voids
        if auto_coinche_active:
            acc.target_score *= 2  # L'Avocat: target doubles
        # The target this blind is actually judged against (2x under
        # L'Avocat). Payout margin, Le Puriste, the big-margin trust check and
        # the [H] history entry must all use it, not the base run target.
        effective_target = acc.target_score

        trust = run.partner.trust
        saved_trust = trust.value
        if lock_trust:
            trust.value = 0  # Le Divorce / La Trahison: freeze trust at 0
        # B4: Reset round-specific trust flags
        trust.auto_capot_used = False

        round_flags = self._round_flags(run)
        # Per-round deal seed drawn from the run's seeded RNG so a whole run
        # (deals + AI play) replays from run.seed — ghost runs depend on it.
        round_seed = run._get_rng().getrandbits(32)
        if self._ghost_recorder is not None:
            self._ghost_recorder.note_round_start(
                run, boss=boss, round_seed=round_seed, target=effective_target
            )
        try:
            final_state = drive_round(
                bus=bus,
                seed=round_seed,
                partner=run.partner,
                boss=boss,
                ui_callbacks=UICallbacks(
                    reader,
                    run,
                    self.profile,
                    self.save_manager,
                    acc,
                    hud,
                    trust_bar,
                    show_north,
                ),
                acc=acc,
                card_enhancements=round_flags,
                recorder=self._ghost_recorder,
            )
        finally:
            # Restore even if the round aborts (e.g. FitAbortedError), so a
            # lock_trust boss can't leave trust frozen at 0.
            if lock_trust:
                trust.value = saved_trust

        # Le Diable tarot is one-round only — consume after the round so the
        # partner doesn't permanently over-cut for the rest of the run.
        run.card_enhancements.pop("partner_overcut_round", None)
        self._announce_heist_outcome(final_state, acc, reader)

        from belote.scoring import score_round

        total = acc.get_total(final_state)
        bd = score_round(final_state)
        # 4.8.0 / B4: snapshot for the trust-bar tick animation below.
        pre_trust_value = trust.value
        self._harvest_round_state(run, final_state)

        survived_via_insurance = False
        if total < effective_target:
            survived_via_insurance = self._settle_failed_blind(
                run, reader, final_state, bd, total, effective_target, lock_trust
            )
        else:
            self._settle_won_blind(
                run, final_state, total, effective_target, auto_coinche_active, lock_trust
            )
        if boss is not None and total >= effective_target and not run.challenge:
            self.unlock_tracker.notify_boss_defeated()
        # Partner-specific trust events (skipped under Le Divorce)
        if not lock_trust:
            if bd.taker_team == 0 and bd.is_failed:
                trust.chute()
            elif bd.is_capot and bd.taker_team == 0:
                trust.capot_together()

        # 4.8.0 / B4: animate the trust bar from its pre-round value to its
        # post-round value. No-op when nothing changed.
        if trust.value != pre_trust_value:
            trust_bar.animate_change(pre_trust_value, reader)

        # 3.3.0: append a BelAtro-side history entry (the [H] overlay reads
        # `run.history` via the override hook installed in `start()`).
        self._record_history_entry(
            ante=history_ante,
            blind_index=history_blind_index,
            target=effective_target,
            boss=boss,
            final_state=final_state,
            bd=bd,
            total=total,
            money_delta=run.economy.money - money_before,
            survived_via_insurance=survived_via_insurance,
        )
        if self._ghost_recorder is not None and run.history:
            self._ghost_recorder.note_round_result(run, run.history[-1], final_state)

    # ── _play_blind phases ──────────────────────────────────────────────

    @staticmethod
    def _roll_ante_theme(run: BelAtroRun) -> None:
        """Phase 3.1: roll an Ante theme at the start of each ante (blind 0),
        from the run's seeded RNG; later blinds of the ante reuse it."""
        from .run.ante_themes import clear_theme_flags, roll_theme

        # Drop the previous ante's theme flags so they don't outlive it
        # (Le Tournoi's coinche offer used to stick for the whole run).
        clear_theme_flags(run)
        theme = roll_theme(run._get_rng().random())
        run.ante_theme = theme.id if theme is not None else None
        if theme is not None:
            theme.on_ante_start(run)

    @staticmethod
    def _build_accumulator(run: BelAtroRun) -> ScoreAccumulator:
        from typing import cast

        from belote.belatro.core.scoring import ContractReward

        acc = ScoreAccumulator()
        acc.deck_id = run.deck_id
        acc.carnet_active = run.show_north_hand
        acc.target_score = run.target_score
        # `run.contract_levels` is typed as the wider `dict[str, dict[str, Any]]`
        # to avoid an import cycle; the accumulator's TypedDict reads are
        # checked at the consumer side.
        acc.contract_levels = cast("dict[str, ContractReward]", run.contract_levels)
        # Le Café's petit-blind +25 chips applies to that one blind only.
        active_theme = run.get_ante_theme()
        theme_chips = active_theme.chips_bonus(run.blind_index) if active_theme else 0
        acc.permanent_chips = run.permanent_chips + theme_chips
        acc.permanent_mult = run.permanent_mult
        # 4.7.0: snapshot interest_rate so the Dix de Der Heist multiplier is
        # fixed for the round (a mid-round La Voûte purchase shouldn't pump an
        # already-resolved heist).
        acc.interest_rate = run.economy.interest_rate
        acc.attach_jokers(run.jokers + run.partner.jokers)
        return acc

    @staticmethod
    def _pick_boss(run: BelAtroRun, reader: KeyReader) -> BossModifier | None:
        """Pick (and reveal) this blind's boss, or None for a plain blind."""
        # Le Joueur deck (`boss_every_2`) adds an extra boss blind on the Big
        # Blind of even-numbered antes — see decks.py. Boss Rush (4.11.0)
        # makes every blind a boss blind.
        is_boss_blind = (
            run.blind_index == 2
            or run.boss_rush
            or (
                bool(run.card_enhancements.get("boss_every_2"))
                and run.blind_index == 1
                and run.ante_number % 2 == 0
            )
        )
        if not is_boss_blind:
            return None
        # La Maison-Dieu tarot (used in the previous shop) replaces the
        # upcoming boss with a plain blind. One-shot: consume the flag and
        # deliberately skip the reveal animation.
        if run.card_enhancements.pop("disable_next_boss", False):
            return None

        from .run.boss import take_upcoming_boss
        from .ui.announce import BelAtroAnnounce

        # Seeded run RNG; endless mode rejects a pick from the last-2 window
        # (see run/boss.py::roll_boss). 4.11.0: Le Juge may already have
        # rolled — and rerolled — this boss from the shop.
        boss = take_upcoming_boss(run)
        if run.profile is not None:
            run.profile.discover(boss.id)  # Collection → Bosses tab
        BelAtroAnnounce.boss_reveal(boss, reader)
        return boss

    @staticmethod
    def _round_flags(run: BelAtroRun) -> dict[str, object]:
        """Run-level deck/voucher/joker flags surfaced into the round's
        joker_state so scoring/legal_cards/round_driver can honor them."""
        round_flags: dict[str, object] = dict(run.card_enhancements)
        # 4.5.0: LePrêteur gates its $0/$50 branches on this. Snapshotted
        # PRE-round so the joker's own payout doesn't feed its threshold.
        round_flags["current_money"] = run.economy.money
        if run.tie_breaks_for_taker:
            round_flags["tie_breaks_for_taker"] = True
        if run.show_partner_bid_tendency:
            personality = run.partner.personality
            round_flags["partner_bid_tendency_text"] = (
                f"Partner ({personality.name}): {personality.description}"
            )
        # Le Traître / L'Agent Double jokers: partner sabotages one / two
        # random tricks; round_driver picks them and reuses the agent_double path.
        if run.partner_throws_trick:
            round_flags["traitre_active"] = True
        if run.agent_double_joker:
            round_flags["agent_double_joker_active"] = True
        if run.surcoinche_unlocked:
            round_flags["surcoinche_unlocked"] = True
        return round_flags

    @staticmethod
    def _announce_heist_outcome(
        final_state: BelatroState, acc: ScoreAccumulator, reader: KeyReader
    ) -> None:
        """4.7.0 heist banner. The multiplier/forfeit is already applied by the
        accumulator; this is the narrative beat. Suppressed under Le Brouillard
        (`hide_hud`), whose promise is to hide the score."""
        from .ui.announce import BelAtroAnnounce

        outcome = final_state._joker_state.get("heist_outcome")
        if outcome is None or final_state.variants.hide_hud:
            return
        if outcome == "won":
            BelAtroAnnounce.banner(
                f"HEIST SECURED ×{1 + acc.interest_rate} — Dix de Der pays out",
                reader,
                hold=2.0,
            )
        elif outcome == "lost":
            raw_forfeit = final_state._joker_state.get("heist_ns_trick_chips", 0)
            forfeit = raw_forfeit if isinstance(raw_forfeit, int) else 0
            BelAtroAnnounce.banner(
                f"HEIST BUSTED — tricks 1-7 forfeited (-{forfeit} chips)",
                reader,
                color="red",
                hold=2.0,
            )

    @staticmethod
    def _harvest_round_state(run: BelAtroRun, final_state: BelatroState) -> None:
        """Carry per-round joker_state results back into the run."""
        # Phase 2.2: drain pending Tierce charges into the run state.
        pending = final_state._joker_state.get("_pending_tierce_charge", 0)
        if isinstance(pending, int) and pending > 0:
            run.tierce_charges += pending
        # Phase 2.1: persist Tout Atout streak between rounds.
        streak = final_state._joker_state.get("tout_streak_streak", 0)
        if isinstance(streak, int):
            run.card_enhancements["tout_streak_streak"] = streak
        # 4.11.0: run-scoped joker counters (L'Horloger, ...) ride on
        # card_enhancements between rounds, like the Tout Atout streak.
        from .items.jokers.tempo import PERSISTENT_JOKER_KEYS

        for key in PERSISTENT_JOKER_KEYS:
            value = final_state._joker_state.get(key)
            if isinstance(value, int):
                run.card_enhancements[key] = value
        # Phase 2.3: refresh partner_mood for HUD display.
        run.partner_mood = run.partner.trust.mood()

    def _settle_failed_blind(
        self,
        run: BelAtroRun,
        reader: KeyReader,
        final_state: BelatroState,
        bd: ScoringBreakdown,
        total: int,
        effective_target: int,
        lock_trust: bool,
    ) -> bool:
        """Target missed. Returns True when Capot Insurance saved the run."""
        from .ui.announce import BelAtroAnnounce

        survived = False
        # Phase 2.1: Capot Insurance halves the chute loss (one-shot) and defers
        # run-over by one blind.
        if bd.is_failed and run.capot_insurance:
            run.capot_insurance = False
            survived = True
            BelAtroAnnounce.banner(
                "[Assurance Capot] Chute pénalité divisée par deux — round survived.",
                reader,
                hold=2.0,
            )
            # The run continues past this chute. Reconcile signed joker money
            # (e.g. LePreteur's -$5 skim, baked into the round's ×Mult) so the
            # player isn't handed a free multiplier. spend_money no-ops if broke.
            self._reconcile_bonus_money(final_state._bonus_money)
        else:
            run.run_over = True
            BelAtroAnnounce.banner(
                f"RUN OVER — Failed to meet target {effective_target} (scored {total}).",
                reader,
                color="red",
                hold=2.5,
            )
        if not lock_trust:
            run.partner.trust.blind_failed()
        return survived

    def _settle_won_blind(
        self,
        run: BelAtroRun,
        final_state: BelatroState,
        total: int,
        effective_target: int,
        auto_coinche_active: bool,
        lock_trust: bool,
    ) -> None:
        # The theme hook measures this blind's payout only; the history entry
        # uses the pre-round `money_before` snapshot so money_delta is computed
        # the same way on win and loss (incl. L'Architecte's mid-bid $10).
        money_before_payout = run.economy.money
        margin = total - effective_target
        payout = run.economy.process_round_end(margin)
        if auto_coinche_active:
            run.economy.add_money(payout * 2)  # L'Avocat: triple total payout
        self._reconcile_bonus_money(final_state._bonus_money)
        if final_state._joker_state.get("puriste_triggered"):
            run.economy.add_money(max(0, margin // 10))  # Le Puriste: double base payout
        # L'Aristocrate deck: +$1 per Ace captured by NS team this round.
        if run.gold_seal_aces:
            aces_won = _aces_won_by_team(final_state, team=0)
            if aces_won > 0:
                run.economy.add_money(aces_won)
        if not lock_trust:
            if total >= effective_target * 1.5:
                run.partner.trust.big_margin_win()
            else:
                run.partner.trust.blind_beaten()
        # Phase 3.1: the ante theme's per-blind-won hook (Tournoi bonus money,
        # Café +1 trust on big-blind wins).
        theme = run.get_ante_theme()
        if theme is not None:
            theme.on_blind_won(run, run.blind_index, run.economy.money - money_before_payout)

    def _record_history_entry(
        self,
        *,
        ante: int,
        blind_index: int,
        target: int,
        boss: BossModifier | None,
        final_state: BelatroState,
        bd: ScoringBreakdown,
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
        from belote.deck import Contract

        boss_name = boss.name if boss is not None else None

        taker = final_state.taker
        if taker is None:
            taker_label = "—"
        else:
            team = "NS" if taker.value % 2 == 0 else "EW"
            taker_label = f"{taker.name[0]} ({team})"

        contract_field = final_state.contract
        trump = final_state.trump
        if contract_field == Contract.SANS_ATOUT:
            contract_str = "SA"
        elif contract_field == Contract.TOUT_ATOUT:
            contract_str = "TA"
        elif trump is not None:
            contract_str = trump.symbol
        else:
            contract_str = "—"

        if total >= target and bd.is_capot and bd.taker_team == 0:
            status = "CAPOT"
        elif total >= target:
            status = "WON"
        elif survived_via_insurance:
            status = "SURVIVED"
        else:
            status = "FAILED"

        # ScoringBreakdown doesn't carry per-team declaration summaries; the
        # renderer shows empty tuples as "─".
        decl_ns: tuple[str, ...] = ()
        decl_ew: tuple[str, ...] = ()

        self.run.history.append(
            BelAtroHistoryEntry(
                ante=ante,
                blind_label=blind_label,
                target=target,
                boss_name=boss_name,
                taker_label=taker_label,
                contract=contract_str,
                tricks_ns=bd.tricks_ns,
                tricks_ew=bd.tricks_ew,
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

    from .integration import install

    install()
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
