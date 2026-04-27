from __future__ import annotations

import re

_RESET_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

RESET = "\x1b[0m"


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
    return bg(20, 90, 50)


def red_fg() -> str:
    return fg(220, 60, 60)


def black_fg() -> str:
    return fg(20, 20, 20)


def card_face_bg() -> str:
    return bg(245, 245, 235)


def face_card_bg() -> str:
    return bg(255, 245, 180)


def card_back_bg() -> str:
    return bg(120, 30, 30)


def highlight_bg() -> str:
    return bg(240, 200, 80)


def gold_fg() -> str:
    return fg(240, 200, 80)


def white_fg() -> str:
    return fg(240, 240, 240)


def light_gray_fg() -> str:
    return fg(180, 180, 180)


def green_fg() -> str:
    return fg(80, 220, 120)


def banner_bg() -> str:
    return bg(60, 60, 180)


def banner_fg() -> str:
    return fg(255, 255, 100)
