"""Spacious-layout HUD must never exceed term_w.

At 120-143 cols the verbose HUD (3-digit scores, litige chip, long theme
name) overflowed term_w: the row wrapped and the alt screen scrolled. The
HUD now drops the theme label, then the key hints, then clamps.
"""

from __future__ import annotations

import dataclasses
import importlib
import random

import pytest

from belote.ansi import visible_len
from belote.deck import Suit
from belote.game import Seat, new_game, start_round
from belote.themes import theme_manager
from belote.ui.layout import SPACIOUS

# `belote.ui.render` the module is shadowed by the re-exported `render`
# function on the package, so fetch the module explicitly.
render_mod = importlib.import_module("belote.ui.render")


def _wide_state() -> object:
    st = start_round(new_game(target=1000), random.Random(1))
    return dataclasses.replace(
        st,
        team_scores=(980, 990),
        current_round_points=(152, 162),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        litige_points=81,
    )


@pytest.mark.parametrize("term_w", [120, 125, 130, 143])
def test_hud_rows_fit_with_wide_scores(term_w: int) -> None:
    st = _wide_state()
    original = theme_manager.current_name
    try:
        for name in theme_manager.list_themes():
            theme_manager._current_theme_name = name
            hud = render_mod._build_hud(st, term_w, SPACIOUS)  # type: ignore[arg-type]
            for row in hud.split("\n"):
                assert visible_len(row) <= term_w, (name, visible_len(row))
    finally:
        theme_manager._current_theme_name = original


def test_full_frame_rows_fit_at_120_cols() -> None:
    from belote.context import TERMINAL

    st = _wide_state()
    saved = TERMINAL._size_cache
    TERMINAL._size_cache = (120, 48)
    try:
        render_mod.render(st)  # type: ignore[arg-type]
        rows = render_mod._pending_rendered_lines
    finally:
        TERMINAL._size_cache = saved
    assert rows
    assert all(visible_len(r) <= 120 for r in rows)


def test_hud_keeps_theme_when_it_fits() -> None:
    st = start_round(new_game(target=1000), random.Random(1))
    hud = render_mod._build_hud(st, 200, SPACIOUS)
    assert "Theme:" in hud
    assert visible_len(hud) == 199  # historical width: last column left free
