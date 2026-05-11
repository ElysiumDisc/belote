from __future__ import annotations

from typing import TYPE_CHECKING

from belote.ansi import BOLD, RESET, gold_fg, green_fg, move, red_fg, white_fg

if TYPE_CHECKING:
    from ..partner.trust import TrustTrack


# 3.4.0: per-tier glyph + name. Index = TrustTrack.tier (0–4).
_TIER_GLYPHS: tuple[str, ...] = ("✗", "♡", "♥", "♦", "★")
_TIER_NAMES: tuple[str, ...] = ("Méfiant", "Sulking", "Neutre", "Loyal", "Mécène")


def _orange_fg() -> str:
    # Standalone helper — ansi.py doesn't expose an orange yet. Bright yellow
    # SGR (38;5;208) renders close to "orange" on 256-colour terminals; falls
    # back to gold on 16-colour. Cheap inline avoids a wider ansi.py change.
    return "\x1b[38;5;208m"


def _bar_color(value: int) -> str:
    """Four-tier colour ramp: 0–2 cramoisi, 3–4 orange, 5–7 gold, 8–10 emeraude."""
    if value <= 2:
        return str(red_fg())
    if value <= 4:
        return _orange_fg()
    if value <= 7:
        return str(gold_fg())
    return str(green_fg())


class TrustBar:
    """Visualizes the 0-10 Trust Track with a tier glyph and 4-colour gradient."""

    def __init__(self, trust: TrustTrack) -> None:
        self.trust = trust

    def render(self) -> None:
        """Render trust meter at (row 4, col 2)."""
        val = self.trust.value
        tier = self.trust.tier
        filled = "█" * val
        empty = "░" * (10 - val)
        color = _bar_color(val)
        bar = color + filled + white_fg() + empty + RESET
        # Tier glyph leads the bar; bolded for the top two tiers so Loyal/
        # Mécène stand out at a glance.
        glyph = _TIER_GLYPHS[tier]
        glyph_render = (BOLD + color + glyph + RESET) if tier >= 3 else (color + glyph + RESET)

        if self.trust.ai_degraded:
            status = red_fg() + " ⚠ Degraded" + RESET
        elif self.trust.auto_capot_available:
            status = gold_fg() + " ★ Auto-Capot" + RESET
        elif self.trust.shares_void_info:
            status = green_fg() + " ✦ Void Info" + RESET
        else:
            status = ""

        print(
            move(4, 2)
            + white_fg() + "Trust: " + RESET
            + glyph_render + " ["
            + bar
            + white_fg() + "] " + RESET
            + status
        )
