"""4.11.0: on-screen key hints follow Settings → Controls rebinding."""

from __future__ import annotations

from belote import input as inp
from belote.game import new_game
from belote.ui.hud_classic import _build_hud
from belote.ui.layout import SPACIOUS


def test_hud_hint_shows_rebound_keys() -> None:
    assert "[H]Hist [T]Theme [Z]Undo [I]HUD" in _build_hud(new_game(), 200, SPACIOUS)
    try:
        inp.set_bindings({"history": "k", "undo": "u"})
        bar = _build_hud(new_game(), 200, SPACIOUS)
        assert "[K]Hist" in bar and "[U]Undo" in bar
    finally:
        inp.set_bindings({})
