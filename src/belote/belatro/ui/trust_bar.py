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
        color = green_fg() if val > 5 else red_fg()
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
