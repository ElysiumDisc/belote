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
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()

        print(clear_screen(), end="")
        for i in range(1, 10):
            print(move(i, 1) + " ")
        print(move(10, 1) + ansi_center(red_fg() + BOLD + "! BOSS BLIND REVEALED !" + RESET, term_w))
        interruptible_sleep(1.0, reader)
        print(move(13, 1) + ansi_center(gold_fg() + BOLD + boss.name.upper() + RESET, term_w))
        interruptible_sleep(1.0, reader)
        print(move(15, 1) + ansi_center(white_fg() + boss.description + RESET, term_w))
        print(move(20, 1) + ansi_center(BOLD + "[ Press any key to continue ]" + RESET, term_w))
        interruptible_sleep(2.0, reader)

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

    @staticmethod
    def yes_no(prompt: str, reader: KeyReader) -> bool:
        """Centered Y/N prompt. Returns True on Y/Enter, False on N/Esc/Q.

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
        while True:
            event = reader.read()
            if event.key in (Key.ENTER,):
                return True
            if event.key in (Key.ESC, Key.QUIT):
                return False
            if event.key == Key.CHAR and event.char:
                ch = event.char.lower()
                if ch in ("y", "o"):  # Y / O for "Oui"
                    return True
                if ch == "n":
                    return False

    @staticmethod
    def score_popup(lines: list[str], reader: KeyReader) -> None:
        """Show a temporary score breakdown popup."""
        from belote.ui.render import get_term_size

        term_w, term_h = get_term_size()
        if not lines:
            return
        toggle_overlay()
        start_row = 24
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
