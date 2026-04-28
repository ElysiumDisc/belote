from __future__ import annotations

import re

from functools import lru_cache

_RESET_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

RESET = "\x1b[0m"


@lru_cache(maxsize=1024)
def visible_len(s: str) -> int:
    """Return length of string with ANSI escape codes stripped."""
    return len(_RESET_RE.sub("", s))


def ansi_center(s: str, width: int) -> str:
    """Center a string by visible width, ignoring ANSI escape codes."""
    vlen = visible_len(s)
    pad = max(0, width - vlen)
    left = pad // 2
    return " " * left + s


def ansi_ljust(s: str, width: int) -> str:
    """Left-justify a string to `width` visible characters, ANSI-aware.
    Never use str.ljust() on ANSI strings — it counts escape bytes as chars.
    """
    vlen = visible_len(s)
    pad = max(0, width - vlen)
    return s + " " * pad


def fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def bg(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


BOLD = "\x1b[1m"
DIM = "\x1b[2m"
REVERSE = "\x1b[7m"
UNDERLINE = "\x1b[4m"
STRIKETHROUGH = "\x1b[9m"


def move(row: int, col: int) -> str:
    return f"\x1b[{row};{col}H"


def clear_screen() -> str:
    return "\x1b[2J" + move(1, 1)


def clear_line() -> str:
    return "\x1b[2K"


def clear_to_eol() -> str:
    return "\x1b[K"


def hide_cursor() -> str:
    return "\x1b[?25l"


def show_cursor() -> str:
    return "\x1b[?25h"


def alt_screen_on() -> str:
    return "\x1b[?1049h"


def alt_screen_off() -> str:
    return "\x1b[?1049l"


def save_cursor() -> str:
    return "\x1b7"


def restore_cursor() -> str:
    return "\x1b8"


def scroll_region(top: int, bottom: int) -> str:
    return f"\x1b[{top};{bottom}r"


# Palette constants
def felt_bg() -> str:
    return bg(25, 75, 45) # Deeper, more muted green


def red_fg() -> str:
    return fg(190, 45, 45) # Muted crimson


def black_fg() -> str:
    return fg(40, 40, 40) # Slightly softer black


def card_face_bg() -> str:
    return bg(248, 245, 230) # Richer cream/parchment


def face_card_bg() -> str:
    return bg(250, 240, 200) # Golden-aged parchment


def card_back_bg() -> str:
    return bg(110, 35, 35) # Deep burgundy


def highlight_bg() -> str:
    return bg(230, 190, 70) # Brass/Gold highlight


def gold_fg() -> str:
    return fg(210, 170, 60) # Antique gold


def white_fg() -> str:
    return fg(235, 235, 230) # Off-white


def light_gray_fg() -> str:
    return fg(160, 160, 155) # Muted stone gray


def green_fg() -> str:
    return fg(60, 160, 90) # Sage green


def banner_bg() -> str:
    return bg(50, 65, 120) # Muted royal blue


def banner_fg() -> str:
    return fg(240, 220, 150) # Pale gold text
