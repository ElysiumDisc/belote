"""A small centred list picker (↑/↓ or W/S, Enter, Esc) for sub-menus."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ..ansi import (
    BOLD,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    light_gray_fg,
)
from ..input import Key, KeyReader
from .render import get_term_size, invalidate_diff


def pick_option(
    reader: KeyReader,
    title: str,
    options: Sequence[str],
    *,
    subtitle: str = "",
    selected: int = 0,
) -> int | None:
    """Return the chosen index, or None on Esc / Q / EOF."""
    sel = max(0, min(selected, len(options) - 1))
    try:
        while True:
            _paint(title, subtitle, options, sel)
            ev = reader.read()
            if ev.key in (Key.UP, Key.LEFT):
                sel = (sel - 1) % len(options)
            elif ev.key in (Key.DOWN, Key.RIGHT):
                sel = (sel + 1) % len(options)
            elif ev.key == Key.ENTER:
                return sel
            elif ev.key in (Key.ESC, Key.QUIT, Key.EOF):
                return None
            elif ev.key == Key.CHAR and ev.char and ev.char.isdecimal():
                idx = int(ev.char) - 1
                if 0 <= idx < len(options):
                    return idx
    finally:
        invalidate_diff()


def _paint(title: str, subtitle: str, options: Sequence[str], sel: int) -> None:
    term_w, term_h = get_term_size()
    width = min(term_w, max(len(title), *(len(o) for o in options)) + 10)
    lines = [f"{BOLD}{gold_fg()}{title}{RESET}"]
    if subtitle:
        lines.append(f"{light_gray_fg()}{subtitle}{RESET}")
    lines.append("")
    for i, opt in enumerate(options):
        label = f"{i + 1}. {opt}".ljust(width - 4)
        lines.append(f"{REVERSE} {label} {RESET}" if i == sel else f"  {label}  ")
    lines += ["", f"{light_gray_fg()}↑/↓ Select   Enter Confirm   Esc Back{RESET}"]
    top = max(1, (term_h - len(lines)) // 2)
    out = [clear_screen(), hide_cursor()]
    for i, line in enumerate(lines):
        out.append(f"\x1b[{top + i};1H{ansi_center(line, term_w)}")
    sys.stdout.write("".join(out))
    sys.stdout.flush()
