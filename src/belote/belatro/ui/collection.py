from __future__ import annotations

import sys
from collections.abc import Collection, Sequence
from typing import TYPE_CHECKING, Any

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    menu_art_fg,
    menu_border_fg,
    move,
    visible_len,
    white_fg,
)
from belote.input import Key, key_label
from belote.ui.render import get_term_size, invalidate_diff
from belote.ui.text import wrap_words

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..progression.save import Profile


def collection_top(n_items: int, selected: int, max_rows: int) -> int:
    """First visible row of the item list so `selected` stays on screen.

    Pre-4.10.0 the list was sliced from the selected item itself, pinning the
    cursor to the top row and hiding every item above it.
    """
    if max_rows <= 0 or n_items <= max_rows:
        return 0
    return max(0, min(selected - max_rows + 1, n_items - max_rows))


_TAB_ROW = 5
_LIST_ROW = 7
_LIST_COL = 10


def _list_rows(term_h: int, hint: str) -> int:
    return term_h - 12 - (2 if hint else 0)


def _tab_cells(categories: Sequence[tuple[str, Sequence[Any]]], cat_idx: int) -> list[str]:
    cells = []
    for i, (name, _) in enumerate(categories):
        label = f"[{name}]" if i == cat_idx else f" {name} "
        color = gold_fg() + BOLD if i == cat_idx else white_fg()
        cells.append(color + label + RESET)
    return cells


def collection_regions(
    categories: Sequence[tuple[str, Sequence[Any]]],
    cat_idx: int,
    item_idx: int,
    term_w: int,
    term_h: int,
    hints: dict[str, str] | None = None,
) -> list[Any]:
    """5.0.0 mouse: the tabs ("tab", i) and visible list rows ("item", i)
    of the frame `collection_frame` paints with the same arguments."""
    from belote.ui.hitmap import Region

    cells = _tab_cells(categories, cat_idx)
    regions: list[Any] = []
    col = max(0, (term_w - visible_len("  ".join(cells))) // 2) + 1
    for i, cell in enumerate(cells):
        width = visible_len(cell)
        regions.append(Region(_TAB_ROW, col, 1, width, ("tab", i)))
        col += width + 2
    cat_name, items = categories[cat_idx]
    max_rows = _list_rows(term_h, (hints or {}).get(cat_name, ""))
    top = collection_top(len(items), item_idx, max_rows)
    for i in range(max(0, min(max_rows, len(items) - top))):
        regions.append(
            Region(_LIST_ROW + i, _LIST_COL, 1, max(10, term_w // 2 - 12), ("item", top + i))
        )
    return regions


def collection_frame(
    categories: Sequence[tuple[str, Sequence[Any]]],
    discovered: Collection[str],
    cat_idx: int,
    item_idx: int,
    term_w: int,
    term_h: int,
    hints: dict[str, str] | None = None,
) -> str:
    """Pure frame builder for the collection gallery (one full repaint).

    `hints` maps a category name to a one-line teaser painted under its list
    (4.11.0: the secret joker's riddle while it is still hidden)."""
    cat_name, items = categories[cat_idx]
    out = [clear_screen(), hide_cursor()]

    # Header
    title = f"COLLECTION - {cat_name} ({len(discovered)} Discovered)"
    out.append(move(2, 1) + ansi_center(gold_fg() + BOLD + title + RESET, term_w))
    out.append(move(3, 1) + ansi_center(menu_border_fg() + "─" * (len(title) + 4) + RESET, term_w))

    # Category tabs
    out.append(move(_TAB_ROW, 1) + ansi_center("  ".join(_tab_cells(categories, cat_idx)), term_w))

    # Item list (scrolls to keep the selection visible)
    start_row = _LIST_ROW
    hint = (hints or {}).get(cat_name, "")
    max_rows = _list_rows(term_h, hint)
    top = collection_top(len(items), item_idx, max_rows)
    for i, item_cls in enumerate(items[top : top + max(0, max_rows)]):
        real_idx = top + i
        is_discovered = item_cls.id in discovered
        prefix = "> " if real_idx == item_idx else "  "
        color = white_fg() if is_discovered else DIM
        name = item_cls.name if is_discovered else "???"
        out.append(move(start_row + i, _LIST_COL) + color + prefix + name + RESET)

    # Details for the selected item on the right
    if items:
        out.extend(_detail_panel(items[item_idx], discovered, start_row, term_w))

    if hint:
        out.append(move(term_h - 4, 1) + ansi_center(DIM + "✦ " + hint + RESET, term_w))

    # Footer
    out.append(
        move(term_h - 1, 1)
        + ansi_center(
            light_gray_fg() + f"←/→: Category  ↑/↓: Item  Esc/{key_label('quit')}: Back" + RESET,
            term_w,
        )
    )
    return "".join(out)


def _detail_panel(
    item_cls: Any, discovered: Collection[str], start_row: int, term_w: int
) -> list[str]:
    info_col = max(40, term_w // 2)
    if item_cls.id not in discovered:
        return [
            move(start_row, info_col) + DIM + "??? (Undiscovered)" + RESET,
            move(start_row + 2, info_col) + DIM + "Keep playing to find this item!" + RESET,
        ]
    wrap_w = max(20, term_w - info_col - 2)
    out = [
        move(start_row, info_col) + gold_fg() + BOLD + item_cls.name + RESET,
        move(start_row + 1, info_col) + menu_border_fg() + "─" * min(30, wrap_w) + RESET,
    ]
    art = getattr(item_cls, "ascii_art", []) or []
    for j, art_line in enumerate(art):
        out.append(move(start_row + 2 + j, info_col) + menu_art_fg() + art_line + RESET)
    desc_start = start_row + 2 + len(art) + 1
    desc = getattr(item_cls, "description", "No description.")
    for r, line in enumerate(wrap_words(desc, wrap_w)):
        out.append(move(desc_start + r, info_col) + white_fg() + line + RESET)
    return out


def collection_categories(
    profile: Profile,
) -> tuple[list[tuple[str, list[Any]]], dict[str, str]]:
    """Gallery tabs and per-tab hints for `profile`.

    4.11.0: secret jokers are left out entirely (not even a "???" row) until
    the profile unlocks them; their riddle shows as the Jokers tab hint
    instead. Bosses get their own tab (discovered when first faced).
    """
    from ..items.registry import registry
    from ..run.boss import ALL_BOSS_MODIFIERS
    from ..run.fusion import RECIPES, OathEntry
    from ..run.medals import MEDALS

    jokers: list[Any] = []
    riddles: list[str] = []
    for cls in registry.jokers.values():
        if cls.is_secret and not profile.is_unlocked(cls.id):
            riddles.append(cls.secret_hint)
        else:
            jokers.append(cls)
    # 5.0.0: Le Serment's hidden recipe page (revealed as each fusion is
    # first made) and the Médailles sit next to the Jokers.
    categories: list[tuple[str, list[Any]]] = [
        ("Jokers", jokers),
        ("Recipes", [OathEntry(), *RECIPES]),
        ("Médailles", list(MEDALS.values())),
        ("Tarots", list(registry.tarots.values())),
        ("Planets", list(registry.planets.values())),
        ("Vouchers", list(registry.vouchers.values())),
        ("Bosses", list(ALL_BOSS_MODIFIERS)),
    ]
    hints: dict[str, str] = {"Jokers": riddles[0]} if riddles else {}
    if not all(r.id in profile.discovered_items for r in RECIPES):
        hints["Recipes"] = "Some jokers were made for each other. Own both, then Fuse in the shop."

    return categories, hints


def show_collection(reader: KeyReader, profile: Profile) -> None:
    """Gallery browser for discovered items."""
    from belote.ui.fit_guard import require_minimum

    categories, hints = collection_categories(profile)
    cat_idx = 0
    item_idx = 0
    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        items = categories[cat_idx][1]
        item_idx = min(item_idx, len(items) - 1) if items else 0
        sys.stdout.write(
            collection_frame(
                categories, profile.discovered_items, cat_idx, item_idx, term_w, term_h, hints
            )
        )
        sys.stdout.flush()
        invalidate_diff()
        from belote.ui import hitmap

        hitmap.set_regions(
            "menu", collection_regions(categories, cat_idx, item_idx, term_w, term_h, hints)
        )

        event = reader.read()
        clicked = hitmap.hit("menu", event.pos) if event.key == Key.MOUSE else None
        if isinstance(clicked, tuple):  # 5.0.0: click a tab / an item
            kind, index = clicked
            if kind == "tab" and index != cat_idx:
                cat_idx, item_idx = index, 0
            elif kind == "item":
                item_idx = index
            continue
        match event.key:
            case Key.QUIT | Key.ESC | Key.EOF:
                return
            case Key.LEFT:
                cat_idx = (cat_idx - 1) % len(categories)
                item_idx = 0
            case Key.RIGHT:
                cat_idx = (cat_idx + 1) % len(categories)
                item_idx = 0
            case Key.UP:
                item_idx = max(0, item_idx - 1)
            case Key.DOWN:
                item_idx = min(len(items) - 1 if items else 0, item_idx + 1)
