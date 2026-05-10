from __future__ import annotations

from typing import TYPE_CHECKING

from belote.ansi import RESET, gold_fg, green_fg, move, red_fg, white_fg

if TYPE_CHECKING:
    from ..partner.trust import TrustTrack


class TrustBar:
    """Visualizes the 0-10 Trust Track."""

    def __init__(self, trust: TrustTrack) -> None:
        self.trust = trust

    def render(self) -> None:
        """Render trust meter."""
        val = self.trust.value
        filled = "█" * val
        empty = "░" * (10 - val)
        # Three-tier color: ≤3 red (danger), 4–6 gold (neutral), ≥7 green
        # (healthy). The default trust=5 used to render red under the old
        # `> 5` threshold, which falsely signalled distrust at game start.
        if val <= 3:
            color = red_fg()
        elif val >= 7:
            color = green_fg()
        else:
            color = gold_fg()
        bar = color + filled + white_fg() + empty + RESET

        if self.trust.ai_degraded:
            status = red_fg() + " ⚠ Degraded" + RESET
        elif self.trust.auto_capot_available:
            status = gold_fg() + " ★ Auto-Capot" + RESET
        elif self.trust.shares_void_info:
            status = green_fg() + " ✦ Void Info" + RESET
        else:
            status = ""

        print(
            move(4, 2) + white_fg() + "Trust: [" + RESET + bar + white_fg() + "] " + RESET + status
        )
