"""Live "terminal too small" overlay.

`require_minimum(reader, min_cols, min_rows)` blocks while the terminal is
below the floor, painting a centered prompt that updates whenever the user
resizes (the SIGWINCH handler in `render.py` invalidates the size cache, so
each iteration sees fresh dimensions). Returns immediately once the terminal
is large enough; raises `FitAbortedError` if the user presses Q / Ctrl-C / EOF.

Callers own alt-screen state — this module never enters or exits it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..ansi import (
    BOLD,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    move,
    red_fg,
    white_fg,
)
from ..input import Key
from .render import get_term_size

if TYPE_CHECKING:
    from ..input import KeyReader


class FitAbortedError(Exception):
    """Raised when the user gives up on resizing (Q / Ctrl-C / EOF)."""


def require_minimum(
    reader: KeyReader,
    min_cols: int = 80,
    min_rows: int = 32,
) -> None:
    """Block until the terminal is at least `min_cols × min_rows`.

    Paints a centered "Terminal too small" overlay that refreshes whenever
    the size cache invalidates (SIGWINCH). Returns immediately if the
    terminal is already large enough.
    """
    import sys

    while True:
        cols, rows = get_term_size()
        if cols >= min_cols and rows >= min_rows:
            return

        mid = max(1, rows // 2)
        title = f"{red_fg()}{BOLD}Terminal too small{RESET}"
        body = (
            f"{white_fg()}Please resize to at least "
            f"{gold_fg()}{min_cols}x{min_rows}{RESET}"
            f"{white_fg()} (currently {cols}x{rows}){RESET}"
        )
        hint = f"{white_fg()}Press Q to quit{RESET}"

        sys.stdout.write(
            clear_screen()
            + hide_cursor()
            + move(max(1, mid - 1), 1)
            + ansi_center(title, cols)
            + move(mid + 1, 1)
            + ansi_center(body, cols)
            + move(min(rows, mid + 3), 1)
            + ansi_center(hint, cols)
        )
        sys.stdout.flush()

        event = reader.read_timeout(0.25)
        if event is None:
            continue
        if event.key in (Key.QUIT, Key.EOF):
            raise FitAbortedError
        if event.key == Key.CHAR and event.char and event.char.lower() == "q":
            raise FitAbortedError
