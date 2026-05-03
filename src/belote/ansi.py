from __future__ import annotations

import re
from functools import lru_cache

from .themes import theme_manager

_RESET_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

RESET = "\x1b[0m"


@lru_cache(maxsize=4096)
def visible_len(s: str) -> int:
    """Return length of string with ANSI escape codes stripped."""
    return len(_RESET_RE.sub("", s))


def ansi_center(s: str, width: int) -> str:
    """Center a string by visible width, padding both sides."""
    vlen = visible_len(s)
    pad = max(0, width - vlen)
    left = pad // 2
    right = width - vlen - left
    return " " * left + s + " " * right


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
    """Clear screen and move to top-left."""
    return "\x1b[H\x1b[2J"


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
    return bg(*theme_manager.get_current().felt_bg)


def red_fg() -> str:
    return fg(*theme_manager.get_current().red_fg)


def black_fg() -> str:
    return fg(*theme_manager.get_current().black_fg)


def card_face_bg() -> str:
    return bg(*theme_manager.get_current().card_face_bg)


def face_card_bg() -> str:
    return bg(*theme_manager.get_current().face_card_bg)


def card_back_bg() -> str:
    return bg(*theme_manager.get_current().card_back_bg)


def highlight_bg() -> str:
    return bg(*theme_manager.get_current().highlight_bg)


def gold_fg() -> str:
    return fg(*theme_manager.get_current().gold_fg)


def white_fg() -> str:
    return fg(*theme_manager.get_current().white_fg)


def light_gray_fg() -> str:
    return fg(*theme_manager.get_current().light_gray_fg)


def green_fg() -> str:
    return fg(*theme_manager.get_current().green_fg)


def banner_bg() -> str:
    return bg(*theme_manager.get_current().banner_bg)


def banner_fg() -> str:
    return fg(*theme_manager.get_current().banner_fg)


def felt_placeholder_fg() -> str:
    return fg(*theme_manager.get_current().felt_placeholder_fg)


def menu_art_fg() -> str:
    return fg(*theme_manager.get_current().menu_art_fg)


def menu_border_fg() -> str:
    return fg(*theme_manager.get_current().menu_border_fg)
