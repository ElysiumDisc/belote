from __future__ import annotations

import time
from typing import TYPE_CHECKING

from belote.ansi import BOLD, DIM, RESET, ansi_center, clear_screen, gold_fg, move, red_fg, white_fg
from belote.input import Key, interruptible_sleep
from belote.ui.render import invalidate_diff

if TYPE_CHECKING:
    from belote.game import GameState
    from belote.input import KeyReader

    from ..core.scoring import ScoreAccumulator
    from ..run.boss import BossModifier

OVERLAY = "OVERLAY"

_overlay_visible: bool = False

# 4.6.3: separate flag for the BelAtro top-row overlays (joker pip strip,
# ante/blind/target line, chips×mult score, trust bar, synergy tooltip).
# Default visible; toggled by the I/V key. Kept independent of
# `_overlay_visible` because that flag is owned by the score-popup transient
# and gets flipped on/off inside `score_popup()`.
_top_hud_visible: bool = True


def is_overlay_visible() -> bool:
    return _overlay_visible


def toggle_overlay() -> None:
    global _overlay_visible
    _overlay_visible = not _overlay_visible


def reset_overlay_state() -> None:
    """Reset overlay state to False. Call between tests to prevent state leakage."""
    global _overlay_visible
    _overlay_visible = False


def is_top_hud_visible() -> bool:
    return _top_hud_visible


def toggle_top_hud() -> None:
    global _top_hud_visible
    _top_hud_visible = not _top_hud_visible


def reset_top_hud_state() -> None:
    """Reset top-HUD visibility to True. Call between tests to prevent leakage."""
    global _top_hud_visible
    _top_hud_visible = True


# 4.7.0: Slot-machine tally state. Module-level so the per-trick animation
# can resume from the previous total without reading state. `None` means
# the next call seeds from 0 (round start). Reset via reset_tally_state().
_last_tally_total: int | None = None

# 4.7.0 follow-up: final-frame text lines from the most recent tally
# animation, persisted in the HUD region between tricks. Read by
# `BelAtroHUD.render()` (gated on `is_top_hud_visible()`), so pressing `I`
# hides both the top HUD and the persistent tally readout in one shot.
# Cleared at round start alongside `_last_tally_total`. Overwritten at the
# end of every subsequent `slot_machine_tally` call.
_last_tally_readout: list[str] | None = None


def reset_tally_state() -> None:
    """Reset the slot-machine tally cache. Call at round start in `_play_blind`
    and between tests to prevent leakage from a prior round/test."""
    global _last_tally_total, _last_tally_readout
    _last_tally_total = None
    _last_tally_readout = None


class BelAtroAnnounce:
    """Handles announcements and popups."""

    @staticmethod
    def boss_reveal(boss: BossModifier, reader: KeyReader) -> None:
        """Dramatically reveal a boss blind."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        mid = max(4, term_h // 2)

        print(clear_screen(), end="")
        print(
            move(mid - 3, 1)
            + ansi_center(red_fg() + BOLD + "! BOSS BLIND REVEALED !" + RESET, term_w)
        )
        interruptible_sleep(1.0, reader)
        print(move(mid, 1) + ansi_center(gold_fg() + BOLD + boss.name.upper() + RESET, term_w))
        interruptible_sleep(1.0, reader)
        print(move(mid + 2, 1) + ansi_center(white_fg() + boss.description + RESET, term_w))
        print(
            move(max(mid + 5, term_h - 2), 1)
            + ansi_center(BOLD + "[ Press any key to continue ]" + RESET, term_w)
        )
        interruptible_sleep(2.0, reader)
        invalidate_diff()

    @staticmethod
    def banner(message: str, reader: KeyReader, *, color: str = "gold", hold: float = 1.5) -> None:
        """Show a centered banner that doesn't scroll the alt-screen buffer."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        row = max(1, term_h // 2)
        tint = gold_fg() if color != "red" else red_fg()
        print(move(row, 1) + ansi_center(tint + BOLD + message + RESET, term_w), end="", flush=True)
        end = time.time() + hold
        remaining = end - time.time()
        while remaining > 0:
            event = reader.read_timeout(remaining)
            if event is None:
                break
            if event.key in (Key.SPACE, Key.ESC, Key.ENTER, Key.EOF):
                break
            remaining = end - time.time()
        invalidate_diff()

    @staticmethod
    def buy_contract_picker(reader: KeyReader) -> object:
        """L'Architecte buy-contract picker.

        Returns a contract value compatible with `process_bid`:
        - `Suit.SPADES` / `HEARTS` / `DIAMONDS` / `CLUBS` for normal contracts
        - `Suit.TOUT_ATOUT` for Tout Atout
        - the `SANS_ATOUT_BID` string sentinel for Sans Atout
        - `None` if the user cancels (Esc / Q / EOF)

        4.5.0 — UI lives here (not `belote/ui/prompts.py`) because the buy is
        a BelAtro-only deck rule.
        """
        from belote.deck import Suit
        from belote.game import SANS_ATOUT_BID
        from belote.ui.render import get_term_size

        options: list[tuple[str, object]] = [
            ("♠ Spades", Suit.SPADES),
            ("♥ Hearts", Suit.HEARTS),
            ("♦ Diamonds", Suit.DIAMONDS),
            ("♣ Clubs", Suit.CLUBS),
            ("Tout Atout", Suit.TOUT_ATOUT),
            ("Sans Atout", SANS_ATOUT_BID),
        ]
        sel = 0
        term_w, term_h = get_term_size()
        row = max(1, term_h // 2 - 1)

        try:
            while True:
                print(clear_screen(), end="")
                title = gold_fg() + BOLD + "L'Architecte — Pick a contract ($10)" + RESET
                print(move(row, 1) + ansi_center(title, term_w))
                for i, (label, _) in enumerate(options):
                    marker = "▶ " if i == sel else "  "
                    color = gold_fg() if i == sel else white_fg()
                    line = color + marker + label + RESET
                    print(move(row + 2 + i, 1) + ansi_center(line, term_w))
                hint = white_fg() + "[←↑→↓/WASD] move  [Enter] confirm  [Esc] cancel" + RESET
                print(move(row + 2 + len(options) + 1, 1) + ansi_center(hint, term_w), flush=True)

                event = reader.read()
                if event.key in (Key.UP, Key.LEFT):
                    sel = (sel - 1) % len(options)
                elif event.key in (Key.DOWN, Key.RIGHT):
                    sel = (sel + 1) % len(options)
                elif event.key is Key.ENTER:
                    return options[sel][1]
                elif event.key in (Key.ESC, Key.QUIT, Key.EOF):
                    return None
        finally:
            invalidate_diff()

    @staticmethod
    def yes_no(prompt: str, reader: KeyReader) -> bool:
        """Centered Y/N prompt. Returns True on Y/Enter, False on N/Esc/Q/EOF.

        Repaints in-place — no scroll on alt-screen-strict terminals. Used by
        the post-Ante-8 endless-mode offer.
        """
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        row = max(1, term_h // 2)
        body = gold_fg() + BOLD + prompt + RESET
        hint = white_fg() + "[Y]es / [N]o" + RESET
        print(move(row, 1) + ansi_center(body, term_w), end="")
        print(move(row + 2, 1) + ansi_center(hint, term_w), end="", flush=True)
        try:
            while True:
                event = reader.read()
                if event.key in (Key.ENTER,):
                    return True
                if event.key in (Key.ESC, Key.QUIT, Key.EOF):
                    return False
                if event.key == Key.CHAR and event.char:
                    ch = event.char.lower()
                    if ch in ("y", "o"):  # Y / O for "Oui"
                        return True
                    if ch == "n":
                        return False
        finally:
            invalidate_diff()

    @staticmethod
    def score_popup(lines: list[str], reader: KeyReader) -> None:
        """Show a temporary score breakdown popup."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        if not lines:
            return
        toggle_overlay()
        start_row = max(1, term_h - len(lines) - 4)
        for i, line in enumerate(lines):
            print(move(start_row + i, 1) + ansi_center(gold_fg() + line + RESET, term_w))
        end = time.time() + 1.5
        remaining = end - time.time()
        while remaining > 0:
            event = reader.read_timeout(remaining)
            if event is None:
                break
            key = event.key
            if key in (Key.SPACE, Key.ESC, Key.ENTER, Key.EOF):
                break
            remaining = end - time.time()
        toggle_overlay()
        # The popup painted lines directly to stdout. Without resetting the
        # diff baseline, the next display() call diffs the (unchanged) game
        # state against the cached pre-popup baseline, sees no row changes,
        # and writes nothing — leaving the popup lines visible "the whole
        # time" until something forces a full redraw.
        invalidate_diff()

    @staticmethod
    def slot_machine_tally(
        acc: ScoreAccumulator,
        state: GameState,
        reader: KeyReader,
        *,
        points: int,
    ) -> None:
        """4.7.0: Per-trick odometer-style score animation.

        Replaces the static `score_popup` at `on_trick_end`. Animates the
        running total from the previous tally to the current
        `acc.get_total(state)` value over ~600ms (20 frames × 30ms),
        showing the trick's `points` filling a "bucket" bar and the mult
        applied. Skippable on SPACE / ESC / ENTER / EOF.

        Color thresholds on the displayed total:
          - < target × 0.5 : cyan-ish (white_fg in our palette)
          - < target       : white
          - >= target      : gold
          - >= target × 1.2: gold + flame row above the odometer

        Suppressed under `state.boss_modifiers.hide_hud` (Le Brouillard's
        "hide the score" promise) — the round still progresses, just no
        animation. `invalidate_diff()` always runs in the `finally` block
        per the 4.6.4 overlay rule (pinned by
        `tests/test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff`).
        """
        from belote.ui.render import get_term_size

        global _last_tally_total, _last_tally_readout

        # Several gates suppress the animation but still update the cache so
        # the NEXT visible call animates from the correct delta:
        #   - Le Brouillard (hide_hud): the boss promise is "hide the score";
        #     painting an odometer at term_h-3 defeats it.
        #   - La Compétition (separate_scoring): `acc.get_total(state)` is a
        #     running sum across all four seats, but the round's sealed total
        #     uses a per-seat MAX. The animation would mislead the player.
        #     The HUD applies the same gate at belatro/ui/hud.py:171-176.
        #   - term_h < 6: rows would collide with HUD row 1 (audit finding).
        new_total = acc.get_total(state)
        term_w, term_h = get_term_size()
        if (
            state.boss_modifiers.hide_hud
            or state.boss_modifiers.separate_scoring
            or term_h < 6
        ):
            _last_tally_total = new_total
            return

        old_total = _last_tally_total if _last_tally_total is not None else 0
        target = max(1, acc.target_score)  # avoid div-by-zero in threshold math
        chips = acc.current_chips(state)
        mult = acc.current_mult(state)

        # Paint at rows term_h-5..term_h-3, leaving the bottom 2 rows for the
        # existing prompt/hint area. Mirrors score_popup's bottom-anchored
        # placement at `term_h - len(lines) - 4`. Layout is gated by the
        # `term_h < 6` skip above, so these subtractions can't collide with
        # the HUD row.
        row_flame = term_h - 5
        row_bucket = term_h - 4
        row_odometer = term_h - 3

        # Bucket-fill glyph budget: 10-cell bar, scaled to the trick's points
        # so a high-value trick (Jack of trump = 20) fills more than a low
        # one. Capped at 10 cells to keep the layout stable.
        bucket_cells = max(0, min(10, points // 3))  # ~1 cell per 3 pts

        frames = 20
        frame_delay = 0.03  # 30ms → ~600ms total

        # Mutable container used by `_render` to surface the final frame's
        # painted lines back to the outer scope. The `finally` block reads
        # this and stamps `_last_tally_readout` for the HUD to repaint
        # between tricks. List (not tuple) so Python's late-binding closure
        # rules let the inner function mutate it without `nonlocal`.
        final_lines: list[str] = []

        def _render(frame: int) -> None:
            t = frame / frames  # 0.0 → 1.0
            # Ease-out (1 - (1-t)^2) so the number snaps fast then settles.
            eased = 1 - (1 - t) * (1 - t)
            displayed = int(old_total + (new_total - old_total) * eased)

            # Bucket fills during the first third of the animation.
            bucket_fill = int(min(bucket_cells, bucket_cells * (t * 3)))
            bucket_bar = (
                "[" + "█" * bucket_fill + "_" * (bucket_cells - bucket_fill)
                + " " * max(0, 10 - bucket_cells) + "]"
            )

            # Color resolution based on displayed total.
            if displayed >= target:
                tint = gold_fg() + BOLD
            elif displayed >= target // 2:
                tint = white_fg() + BOLD
            else:
                tint = white_fg()

            mult_pulse = BOLD if frame % 2 == 0 else DIM
            bucket_line = (
                white_fg() + f"+{points} chips " + RESET
                + tint + bucket_bar + RESET
                + "   " + mult_pulse + f"× {mult:.1f} Mult" + RESET
            )
            odometer_line = (
                tint + f"►  {displayed}  ◄" + RESET
                + DIM + f"   ({chips} × {mult:.1f})" + RESET
            )
            # Only paint the flame row when it has content. ansi_center("")
            # would paint a `term_w`-wide row of spaces, wasting a screen
            # row and pushing the bucket/odometer rows above the visible
            # area on tight terminals.
            if displayed >= target * 1.2:
                flame_line = red_fg() + BOLD + "≈ ▼ ◆ ▼ ≈" + RESET
                print(move(row_flame, 1) + ansi_center(flame_line, term_w), end="")
            print(move(row_bucket, 1) + ansi_center(bucket_line, term_w), end="")
            print(
                move(row_odometer, 1)
                + ansi_center(odometer_line, term_w),
                end="",
                flush=True,
            )
            # 4.7.0 follow-up: on the final frame, stash a stable, non-
            # pulsing version of the rendered lines so the HUD can repaint
            # them between tricks. Use BOLD (not the alternating pulse) so
            # the persisted line doesn't depend on parity. The flame row
            # is intentionally omitted — it's a transient "moment of joy"
            # accent, not a steady-state readout.
            if frame == frames:
                steady_bucket = (
                    white_fg() + f"+{points} chips " + RESET
                    + tint + bucket_bar + RESET
                    + "   " + BOLD + f"× {mult:.1f} Mult" + RESET
                )
                final_lines.clear()
                final_lines.append(steady_bucket)
                final_lines.append(odometer_line)

        try:
            for frame in range(frames):
                _render(frame)
                event = reader.read_timeout(frame_delay)
                if event is None:
                    continue
                if event.key in (Key.SPACE, Key.ESC, Key.ENTER, Key.EOF):
                    break
            # Always render the final frame so the displayed total matches
            # new_total exactly (skip or natural completion both land here).
            _render(frames)
            # 4.7.0 follow-up: hold the final frame for ~1s so the player
            # can actually read the trick result. Skippable on the same
            # key set the animation honours. The reader.read_timeout call
            # mirrors the per-frame poll above — won't crash under stdin-
            # redirected pytest because we don't call interruptible_sleep.
            hold_event = reader.read_timeout(1.0)
            del hold_event  # we don't need to act on it; it just breaks the wait
        finally:
            # Cache update MUST be in finally — a KeyboardInterrupt or
            # render-time exception mid-animation must not leave the next
            # round animating from a stale baseline. The audit (4.7.0)
            # flagged this as a critical cache-leak path.
            _last_tally_total = new_total
            # 4.7.0 follow-up: stamp the final-frame lines for the HUD to
            # repaint between tricks. Empty `final_lines` (i.e. an
            # exception fired before `_render(frames)` ran) leaves the
            # readout untouched — the previous trick's readout stays
            # visible, which is acceptable degradation.
            if final_lines:
                _last_tally_readout = list(final_lines)
            # 4.6.4 architectural rule: any overlay that paints rows directly
            # MUST invalidate the diff baseline so subsequent display() calls
            # re-emit overwritten rows. Pinned by
            # tests/test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff.
            invalidate_diff()
