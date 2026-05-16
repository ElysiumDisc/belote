from __future__ import annotations

import os
import re
from dataclasses import dataclass
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
    _refresh_theme_cache()


def no_color_active() -> bool:
    return _NO_COLOR

# ── Theme cache ────────────────────────────────────────────────────────────
# Each color flavor (felt_bg, red_fg, etc.) is hit dozens of times per render.
# Pre-3.0.0 each call walked into theme_manager.get_current() (a dict lookup);
# 3.9.5 caches the final ANSI escape *strings* on theme change so palette
# accessors are a single attribute read instead of a tuple-unpack + lru cache hit.
_active_theme: Theme | None = None


@dataclass(frozen=True)
class _Palette:
    felt_bg: str
    felt_edge_bg: str
    red_fg: str
    black_fg: str
    card_face_bg: str
    face_card_bg: str
    card_back_bg: str
    highlight_bg: str
    gold_fg: str
    white_fg: str
    light_gray_fg: str
    green_fg: str
    banner_bg: str
    banner_fg: str
    felt_placeholder_fg: str
    menu_art_fg: str
    menu_border_fg: str


_active_palette: _Palette | None = None


def _refresh_theme_cache() -> None:
    global _active_theme, _active_palette
    _active_theme = theme_manager.get_current()
    t = _active_theme
    _active_palette = _Palette(
        felt_bg=bg(*t.felt_bg),
        felt_edge_bg=bg(*t.felt_edge_bg),
        red_fg=fg(*t.red_fg),
        black_fg=fg(*t.black_fg),
        card_face_bg=bg(*t.card_face_bg),
        face_card_bg=bg(*t.face_card_bg),
        card_back_bg=bg(*t.card_back_bg),
        highlight_bg=bg(*t.highlight_bg),
        gold_fg=fg(*t.gold_fg),
        white_fg=fg(*t.white_fg),
        light_gray_fg=fg(*t.light_gray_fg),
        green_fg=fg(*t.green_fg),
        banner_bg=bg(*t.banner_bg),
        banner_fg=fg(*t.banner_fg),
        felt_placeholder_fg=fg(*t.felt_placeholder_fg),
        menu_art_fg=fg(*t.menu_art_fg),
        menu_border_fg=fg(*t.menu_border_fg),
    )


def _t() -> Theme:
    if _active_theme is None:
        _refresh_theme_cache()
    assert _active_theme is not None
    return _active_theme


def _p() -> _Palette:
    if _active_palette is None:
        _refresh_theme_cache()
    assert _active_palette is not None
    return _active_palette


theme_manager.register_callback(_refresh_theme_cache)

_RESET_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

RESET = "\x1b[0m"


@lru_cache(maxsize=4096)
def visible_len(s: str) -> int:
    """Return length of string with ANSI escape codes stripped."""
    if "\x1b" not in s:
        return len(s)
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


# Palette accessors. Read precomputed escape strings from the active palette
# (rebuilt by `_refresh_theme_cache()` via theme_manager's change callback).
def felt_bg() -> str:
    return _p().felt_bg


def felt_edge_bg() -> str:
    return _p().felt_edge_bg


def red_fg() -> str:
    return _p().red_fg


def black_fg() -> str:
    return _p().black_fg


def card_face_bg() -> str:
    return _p().card_face_bg


def face_card_bg() -> str:
    return _p().face_card_bg


def card_back_bg() -> str:
    return _p().card_back_bg


def highlight_bg() -> str:
    return _p().highlight_bg


def gold_fg() -> str:
    return _p().gold_fg


def white_fg() -> str:
    return _p().white_fg


def light_gray_fg() -> str:
    return _p().light_gray_fg


def green_fg() -> str:
    return _p().green_fg


def banner_bg() -> str:
    return _p().banner_bg


def banner_fg() -> str:
    return _p().banner_fg


def felt_placeholder_fg() -> str:
    return _p().felt_placeholder_fg


def menu_art_fg() -> str:
    return _p().menu_art_fg


def menu_border_fg() -> str:
    return _p().menu_border_fg
