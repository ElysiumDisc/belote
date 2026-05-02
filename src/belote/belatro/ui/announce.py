from __future__ import annotations

import time
from typing import TYPE_CHECKING

from belote.ansi import BOLD, RESET, ansi_center, clear_screen, gold_fg, move, red_fg, white_fg
from belote.input import Key, interruptible_sleep

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..run.boss import BossModifier

OVERLAY = "OVERLAY"

_overlay_visible: bool = False


def is_overlay_visible() -> bool:
    return _overlay_visible


def toggle_overlay() -> None:
    global _overlay_visible
    _overlay_visible = not _overlay_visible


def reset_overlay_state() -> None:
    """Reset overlay state to False. Call between tests to prevent state leakage."""
    global _overlay_visible
    _overlay_visible = False


class BelAtroAnnounce:
    """Handles announcements and popups."""

    @staticmethod
    def boss_reveal(boss: BossModifier, reader: KeyReader) -> None:
        """Dramatically reveal a boss blind."""
        clear_screen()
        for i in range(1, 10):
            print(move(i, 1) + " ")
        print(move(10, 1) + ansi_center(red_fg() + BOLD + "! BOSS BLIND REVEALED !" + RESET, 80))
        interruptible_sleep(1.0, reader)
        print(move(13, 1) + ansi_center(gold_fg() + BOLD + boss.name.upper() + RESET, 80))
        interruptible_sleep(1.0, reader)
        print(move(15, 1) + ansi_center(white_fg() + boss.description + RESET, 80))
        print(move(20, 1) + ansi_center(BOLD + "[ Press any key to continue ]" + RESET, 80))
        interruptible_sleep(2.0, reader)

    @staticmethod
    def score_popup(lines: list[str], reader: KeyReader) -> None:
        """Show a temporary score breakdown popup."""
        if not lines:
            return
        toggle_overlay()
        start_row = 24
        for i, line in enumerate(lines):
            print(move(start_row + i, 1) + ansi_center(gold_fg() + line + RESET, 80))
        end = time.time() + 1.5
        remaining = end - time.time()
        while remaining > 0:
            event = reader.read_timeout(remaining)
            if event is None:
                break
            key = event.key
            if key in (Key.SPACE, Key.ESC, Key.ENTER):
                break
            remaining = end - time.time()
        toggle_overlay()
