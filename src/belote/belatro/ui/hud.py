from __future__ import annotations

from typing import TYPE_CHECKING

from belote.ansi import BOLD, DIM, RESET, gold_fg, move, red_fg, visible_len, white_fg
from belote.ui.layout import choose_layout

if TYPE_CHECKING:
    from belote.game import GameState

    from ..core.run_state import BelAtroRun
    from ..core.scoring import ScoreAccumulator


_BLIND_NAMES = ["Small Blind", "Big Blind", "Boss Blind"]

_MOOD_GLYPH = {
    "degraded": "✗",
    "sulking": "·",
    "neutral": "○",
    "eager": "●",
    "elated": "★",
}


class BelAtroHUD:
    """Renders the roguelite HUD elements during gameplay."""

    def __init__(self, run: BelAtroRun) -> None:
        self.run = run

    def render(self, acc: ScoreAccumulator, state: GameState) -> None:
        """Render HUD elements, with verbosity scaled to the current layout."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        layout = choose_layout(term_w, term_h)
        run = self.run

        if layout.hud_style == "compact":
            self._render_compact(acc, state, term_w)
            return

        # Standard / verbose path (current behaviour, with a small mood glyph
        # appended to the row-2 left).
        target_str = str(run.target_score)
        mood = _MOOD_GLYPH.get(run.partner_mood, "○")
        print(
            move(2, 2)
            + white_fg()
            + "Ante: "
            + RESET
            + gold_fg()
            + str(run.ante_number)
            + "/8"
            + RESET
            + "   "
            + white_fg()
            + "Blind: "
            + RESET
            + gold_fg()
            + run.current_blind.name
            + RESET
            + "   "
            + white_fg()
            + "Target: "
            + RESET
            + gold_fg()
            + target_str
            + RESET
            + "   "
            + DIM
            + f"Partner: {mood}"
            + RESET
        )

        # Row 3: Score (hidden by Le Brouillard boss)
        if not state.boss_modifiers.hide_hud:
            score_str = f"{state._chips} x {state._mult:.1f} = {acc.get_total(state)}"
            score_col = max(2, term_w - len(score_str) - 2)
            print(move(3, score_col) + red_fg() + BOLD + score_str + RESET)

        # Show jokers on row 2 right side as compact list (full names at standard,
        # truncated names at compact widths).
        if run.jokers:
            names = "  ".join(j.name for j in run.jokers)
            print(move(2, max(2, term_w // 2)) + gold_fg() + names[: term_w // 2 - 2] + RESET)

    def _render_compact(self, acc: ScoreAccumulator, state: GameState, term_w: int) -> None:
        """Compact HUD: single-line summary, joker count instead of names.

        Press J for the full joker list (handled by the gameplay loop, not here).
        """
        run = self.run
        mood = _MOOD_GLYPH.get(run.partner_mood, "○")
        # Row 2: ultra-short summary on the left
        left = (
            f"{white_fg()}A{RESET}{gold_fg()}{run.ante_number}/8{RESET} "
            f"{white_fg()}B{RESET}{gold_fg()}{run.current_blind.name[0]}{RESET} "
            f"{white_fg()}T{RESET}{gold_fg()}{run.target_score}{RESET} "
            f"{DIM}P:{mood}{RESET}"
        )
        # Joker count on the right
        if run.jokers:
            joker_label = f"{gold_fg()}J:{len(run.jokers)}/{run.joker_slots}{RESET} {DIM}[J]{RESET}"
        else:
            joker_label = f"{DIM}J:0/{run.joker_slots}{RESET}"

        # Compose both halves on row 2
        print(move(2, 2) + left)
        right_col = max(2, term_w - visible_len(joker_label) - 1)
        print(move(2, right_col) + joker_label)

        # Row 3: chips × mult on the right (hidden by Le Brouillard)
        if not state.boss_modifiers.hide_hud:
            score_str = f"{state._chips}×{state._mult:.1f}={acc.get_total(state)}"
            score_col = max(2, term_w - len(score_str) - 2)
            print(move(3, score_col) + red_fg() + BOLD + score_str + RESET)
