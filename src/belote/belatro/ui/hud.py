from __future__ import annotations

from typing import TYPE_CHECKING

from belote.ansi import BOLD, RESET, gold_fg, move, red_fg, white_fg

if TYPE_CHECKING:
    from belote.game import GameState

    from ..core.run_state import BelAtroRun
    from ..core.scoring import ScoreAccumulator


_BLIND_NAMES = ["Small Blind", "Big Blind", "Boss Blind"]


class BelAtroHUD:
    """Renders the roguelite HUD elements during gameplay."""

    def __init__(self, run: BelAtroRun) -> None:
        self.run = run

    def render(self, acc: ScoreAccumulator, state: GameState) -> None:
        """Render HUD elements."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        run = self.run
        # Row 2: Ante and blind info
        target_str = str(run.target_score)
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
        )

        # Row 3: Score
        score_str = f"{state._chips} x {state._mult:.1f} = {acc.get_total(state)}"
        score_col = max(2, term_w - len(score_str) - 2)
        print(move(3, score_col) + red_fg() + BOLD + score_str + RESET)

        # Show jokers on row 2 right side as compact list
        if run.jokers:
            names = "  ".join(j.name for j in run.jokers)
            print(move(2, max(2, term_w // 2)) + gold_fg() + names[: term_w // 2 - 2] + RESET)
