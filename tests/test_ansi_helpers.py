"""Pure helper tests for ansi.py and themes.py.

Pre-3.0.0 the UI layer had only one rendering test (vertical pad). These cover
the small ANSI-aware string helpers that the rendering code leans on for
column alignment, plus the theme cache invalidation contract.
"""

from __future__ import annotations

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    _refresh_theme_cache,
    _t,
    ansi_center,
    ansi_ljust,
    clear_to_eol,
    felt_bg,
    red_fg,
    visible_len,
)
from belote.themes import THEMES, theme_manager

# ── visible_len: ANSI-aware string length ─────────────────────────────────


def test_visible_len_strips_color_codes() -> None:
    s = f"{red_fg()}A{RESET}"
    assert visible_len(s) == 1


def test_visible_len_handles_plain_string() -> None:
    assert visible_len("hello") == 5


def test_visible_len_handles_empty() -> None:
    assert visible_len("") == 0


def test_visible_len_handles_multiple_codes() -> None:
    s = f"{BOLD}{red_fg()}hi{RESET}{DIM}!{RESET}"
    assert visible_len(s) == 3


# ── ansi_center / ansi_ljust ──────────────────────────────────────────────


def test_ansi_center_pads_both_sides() -> None:
    out = ansi_center("hi", 6)
    # 2 chars centered in 6 → 2 left pad, 2 right pad.
    assert out == "  hi  "


def test_ansi_center_with_color_keeps_visible_width() -> None:
    s = f"{red_fg()}hi{RESET}"
    out = ansi_center(s, 6)
    assert visible_len(out) == 6


def test_ansi_center_no_pad_when_string_exact_width() -> None:
    assert ansi_center("hello", 5) == "hello"


def test_ansi_ljust_pads_right() -> None:
    assert ansi_ljust("hi", 5) == "hi   "


def test_ansi_ljust_no_pad_when_too_long() -> None:
    # Doesn't truncate — just returns string unchanged.
    assert ansi_ljust("hello world", 5) == "hello world"


def test_ansi_ljust_with_color() -> None:
    s = f"{red_fg()}hi{RESET}"
    out = ansi_ljust(s, 5)
    assert visible_len(out) == 5


# ── clear_to_eol ──────────────────────────────────────────────────────────


def test_clear_to_eol_returns_csi_k() -> None:
    assert clear_to_eol() == "\x1b[K"


# ── Theme cache + callback contract ───────────────────────────────────────


def test_theme_cache_initially_populated() -> None:
    assert _t() is not None
    assert _t().name in {t.name for t in THEMES.values()}


def test_theme_change_invalidates_cache_and_callback_fires() -> None:
    """Switching theme must propagate through theme_manager.set_current()
    -> registered callbacks -> _t() returns the new theme."""
    original = theme_manager.current_name
    try:
        # Use any theme that's not the current one.
        targets = [k for k in THEMES if k != original]
        new_name = targets[0]
        theme_manager.set_current(new_name)
        assert _t().name == THEMES[new_name].name
    finally:
        theme_manager.set_current(original)
        # Manually refresh in case the test runner caches between cases.
        _refresh_theme_cache()


def test_themes_have_required_palette_keys() -> None:
    """Every theme must define every palette field — adding a new flavor
    function in ansi.py without updating themes will surface here."""
    required = {
        "felt_bg", "card_face_bg", "face_card_bg", "card_back_bg",
        "highlight_bg", "red_fg", "black_fg", "white_fg", "gold_fg",
        "light_gray_fg", "green_fg", "banner_bg", "banner_fg",
        "felt_placeholder_fg", "menu_art_fg", "menu_border_fg",
    }
    for name, theme in THEMES.items():
        for k in required:
            assert hasattr(theme, k), f"Theme {name} missing {k}"


# ── ANSI flavor functions return non-empty escape strings ─────────────────


def test_felt_bg_returns_csi_sequence() -> None:
    out = felt_bg()
    assert out.startswith("\x1b[48;2;") and out.endswith("m")


def test_red_fg_returns_csi_sequence() -> None:
    out = red_fg()
    assert out.startswith("\x1b[38;2;") and out.endswith("m")


# ── Singleton invariant ───────────────────────────────────────────────────


def test_theme_manager_is_singleton() -> None:
    from belote.themes import ThemeManager

    a = ThemeManager()
    b = ThemeManager()
    assert a is b
    assert a is theme_manager


def test_set_current_unknown_theme_raises() -> None:
    import pytest as _pt

    original = theme_manager.current_name
    try:
        with _pt.raises(ValueError):
            theme_manager.set_current("nope_not_a_theme")
    finally:
        theme_manager.set_current(original)


def test_current_name_returns_string_in_themes() -> None:
    assert theme_manager.current_name in THEMES
