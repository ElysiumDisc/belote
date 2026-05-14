"""Consumables overlay — lets the player activate Tarot/Planet cards.

Without this overlay, every Tarot bought from the shop and every directly-
purchased Planet would accumulate in `run.consumables` with no way to use
them; only the voucher-gated Forge-Tierce path could level a planet. The
overlay is the missing UI that drives `BelAtroRun.consume()`.

Reusable in two contexts:
- Between rounds from the shop screen (`ShopScreen` handles the `C` key).
- Could be opened from the round loop later; not wired today.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    white_fg,
)
from belote.input import Key

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..core.run_state import BelAtroRun


class ConsumablesOverlay:
    """Numbered overlay listing `run.consumables`; activates the chosen one."""

    def __init__(self, run: BelAtroRun, reader: KeyReader) -> None:
        self.run = run
        self.reader = reader

    def open(self) -> bool:
        """Show the overlay and return True iff a consumable was activated.

        Returns False when the tray is empty or the player cancels (Esc/Q).
        """
        from belote.ui.fit_guard import require_minimum
        from belote.ui.layout import vcenter_lines
        from belote.ui.render import get_term_size

        require_minimum(self.reader)

        # Snapshot the list — `run.consume()` mutates `run.consumables`, and
        # we want indices to remain stable for the keypress dispatch below.
        consumables = list(self.run.consumables)
        term_w, term_h = get_term_size()

        lines: list[str] = [ansi_center(gold_fg() + BOLD + "CONSUMABLES" + RESET, term_w), ""]

        if not consumables:
            lines.append(
                ansi_center(
                    white_fg() + "(none — buy Tarot/Planet cards in the shop)" + RESET, term_w
                )
            )
            lines.append("")
            lines.append(ansi_center("Esc to return", term_w))
            sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
            sys.stdout.flush()
            while True:
                event = self.reader.read()
                if event.key in (Key.ESC, Key.QUIT, Key.ENTER, Key.EOF):
                    return False

        lines.append(ansi_center(white_fg() + "Pick one to activate:" + RESET, term_w))
        lines.append("")
        for i, item in enumerate(consumables):
            name = getattr(item, "name", "?")
            desc = getattr(item, "description", "")
            lines.append(ansi_center(white_fg() + f"[{i + 1}] {name}" + RESET, term_w))
            lines.append(ansi_center(white_fg() + f"    {desc}" + RESET, term_w))
        lines.append("")
        lines.append(ansi_center("[1-9] activate   Esc cancel", term_w))

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()

        while True:
            event = self.reader.read()
            if event.key in (Key.ESC, Key.QUIT, Key.EOF):
                return False
            if event.key == Key.CHAR and event.char and event.char.isdigit():
                idx = int(event.char) - 1
                if 0 <= idx < len(consumables):
                    item = consumables[idx]
                    # Pass the run as context so Tarots that need it (none do
                    # today) have access. Planet.use() ignores context.
                    self.run.consume(item, context=self.run)
                    return True
