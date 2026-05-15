from __future__ import annotations

import os
import re
from functools import lru_cache

from .themes import Theme, theme_manager

# Respect https://no-color.org/. Read once at import; tests use
# _refresh_no_color_from_env() after monkeypatch.setenv. Only color escapes
# are suppressed; SGR formatting (BOLD/DIM/etc.) and cursor sequences remain,
# per the spec.
_NO_COLOR: bool = bool(os.environ.get("NO_COLOR", ""))


def _refresh_no_color_from_env() -> None:
    global _NO_COLOR
    _NO_COLOR = bool(os.environ.get("NO_COLOR", ""))


def no_color_active() -> bool:
    return _NO_COLOR

# ── Theme cache ────────────────────────────────────────────────────────────
# Each color flavor (felt_bg, red_fg, etc.) is hit dozens of times per render.
# Pre-3.0.0 each call walked into theme_manager.get_current() (a dict lookup);
# the 16 flavors × tens of cells × dozens of rows added up. Cache the active
# Theme here and invalidate on theme change via theme_manager's callback hook.
_active_theme: Theme | None = None


def _refresh_theme_cache() -> None:
    global _active_theme
    _active_theme = theme_manager.get_current()


def _t() -> Theme:
    if _active_theme is None:
        _refresh_theme_cache()
    assert _active_theme is not None
    return _active_theme


theme_manager.register_callback(_refresh_theme_cache)
_refresh_theme_cache()

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


@lru_cache(maxsize=512)
def _fg_seq(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


@lru_cache(maxsize=512)
def _bg_seq(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


def fg(r: int, g: int, b: int) -> str:
    if _NO_COLOR:
        return ""
    return _fg_seq(r, g, b)


def bg(r: int, g: int, b: int) -> str:
    if _NO_COLOR:
        return ""
    return _bg_seq(r, g, b)


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


# Palette accessors. Each reads the cached active Theme; theme_manager's
# change callback refreshes the cache on `T` keypress / set_current().
def felt_bg() -> str:
    return bg(*_t().felt_bg)


def red_fg() -> str:
    return fg(*_t().red_fg)


def black_fg() -> str:
    return fg(*_t().black_fg)


def card_face_bg() -> str:
    return bg(*_t().card_face_bg)


def face_card_bg() -> str:
    return bg(*_t().face_card_bg)


def card_back_bg() -> str:
    return bg(*_t().card_back_bg)


def highlight_bg() -> str:
    return bg(*_t().highlight_bg)


def gold_fg() -> str:
    return fg(*_t().gold_fg)


def white_fg() -> str:
    return fg(*_t().white_fg)


def light_gray_fg() -> str:
    return fg(*_t().light_gray_fg)


def green_fg() -> str:
    return fg(*_t().green_fg)


def banner_bg() -> str:
    return bg(*_t().banner_bg)


def banner_fg() -> str:
    return fg(*_t().banner_fg)


def felt_placeholder_fg() -> str:
    return fg(*_t().felt_placeholder_fg)


def menu_art_fg() -> str:
    return fg(*_t().menu_art_fg)


def menu_border_fg() -> str:
    return fg(*_t().menu_border_fg)
