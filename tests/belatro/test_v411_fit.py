"""4.11.0 fit pass: the BelAtro screens touched or added this release paint
inside 80x32 and 100x38 (no row below the terminal, no line past its edge)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest

from belote.belatro.progression.save import Profile
from tests.harness import strip_ansi

_MOVE = re.compile(r"\x1b\[(\d+);(\d+)H")
SIZES = [(80, 32), (100, 38)]


def overflow(raw: str, cols: int, rows: int) -> list[str]:
    """Problems in a captured frame: cursor rows past the bottom, or text
    runs (from a cursor move, or a CR/LF-separated line) past the right edge."""
    problems: list[str] = []
    row, col = 1, 1
    pos = 0
    for m in [*_MOVE.finditer(raw), None]:
        chunk = raw[pos : m.start() if m else len(raw)]
        for i, line in enumerate(re.split(r"\r?\n", chunk)):
            text = strip_ansi(line).replace("\r", "")
            start = col if i == 0 else 1
            if text.strip() and start - 1 + len(text.rstrip()) > cols:
                problems.append(f"row {row + i}: {len(text.rstrip())} cols from col {start}")
            if text.strip() and row + i > rows:
                problems.append(f"row {row + i} > {rows}: {text.strip()[:30]!r}")
        if m is None:
            break
        row, col, pos = int(m.group(1)), int(m.group(2)), m.end()
    return problems


def _menu(reader: Any) -> None:
    from belote.belatro.ui.menu import BelAtroMainMenu

    BelAtroMainMenu(reader, Profile()).run()


def _deck_picker(reader: Any) -> None:
    from belote.belatro.ui.menu import BelAtroMainMenu

    BelAtroMainMenu(reader, Profile())._select_deck()


def _collection(reader: Any) -> None:
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.ui.collection import show_collection

    register_all_items()
    show_collection(reader, Profile(discovered_items=["le_contrebandier", "l_huissier"]))


def _boss_rush(reader: Any) -> None:
    from belote.belatro.ui.boss_rush import show_boss_rush

    show_boss_rush(reader, Profile())


def _ghost_picker(reader: Any) -> None:
    from belote.belatro.ui.ghost_viewer import show_ghost_picker

    show_ghost_picker(reader)


SCREENS: dict[str, tuple[Callable[[Any], None], tuple[str, ...]]] = {
    "menu": (_menu, ("down", "esc")),
    "deck-picker": (_deck_picker, ("up", "up", "esc")),  # locked Le Complice panel
    "collection-jokers": (_collection, ("down", "esc")),
    "collection-bosses": (_collection, ("left", "down", "esc")),
    "boss-rush": (_boss_rush, ("right", "down", "left", "down", "right", "esc")),
    "ghost-picker-empty": (_ghost_picker, ("esc",)),
}


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("name", list(SCREENS))
def test_screen_fits(tui: Any, name: str, size: tuple[int, int]) -> None:
    cols, rows = size
    tui.resize(cols, rows)
    screen, script = SCREENS[name]
    screen(tui.reader(*script))
    frames = tui.screen.frames()
    assert frames, name
    for frame in frames:
        assert overflow(frame, cols, rows) == [], name


def test_shop_with_partner_offer_fits(tui: Any) -> None:
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.jokers.rivals import LeContrebandier
    from belote.belatro.items.partner_jokers.passive import LeMiroir
    from belote.belatro.items.planets import Neptune
    from belote.belatro.items.vouchers import LeTelephone
    from belote.belatro.run.shop import Shop
    from belote.belatro.ui.shop import ShopScreen

    for cols, rows in SIZES:
        tui.resize(cols, rows)
        run = BelAtroRun(seed=1)
        shop = Shop(run, Profile())
        partner = LeMiroir()
        partner.for_partner = True
        screen = ShopScreen(shop, tui.reader())
        shop.inventory = [LeContrebandier(), partner, Neptune(), LeTelephone()]
        screen.selected = 1
        screen._render()
        frame = tui.screen.frames()[-1]
        assert overflow(frame, cols, rows) == []
        assert "for partner" in strip_ansi(frame) and "[Partner slot]" in strip_ansi(frame)
        tui.screen.clear()
