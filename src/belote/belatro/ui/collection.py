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
    white_fg,
)
from belote.input import Key
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


def collection_frame(
    categories: Sequence[tuple[str, Sequence[Any]]],
    discovered: Collection[str],
    cat_idx: int,
    item_idx: int,
    term_w: int,
    term_h: int,
) -> str:
    """Pure frame builder for the collection gallery (one full repaint)."""
    cat_name, items = categories[cat_idx]
    out = [clear_screen(), hide_cursor()]

    # Header
    title = f"COLLECTION - {cat_name} ({len(discovered)} Discovered)"
    out.append(move(2, 1) + ansi_center(gold_fg() + BOLD + title + RESET, term_w))
    out.append(move(3, 1) + ansi_center(menu_border_fg() + "─" * (len(title) + 4) + RESET, term_w))

    # Category tabs
    cat_line = []
    for i, (name, _) in enumerate(categories):
        label = f"[{name}]" if i == cat_idx else f" {name} "
        color = gold_fg() + BOLD if i == cat_idx else white_fg()
        cat_line.append(color + label + RESET)
    out.append(move(5, 1) + ansi_center("  ".join(cat_line), term_w))

    # Item list (scrolls to keep the selection visible)
    start_row = 7
    max_rows = term_h - 12
    top = collection_top(len(items), item_idx, max_rows)
    for i, item_cls in enumerate(items[top : top + max(0, max_rows)]):
        real_idx = top + i
        is_discovered = item_cls.id in discovered
        prefix = "> " if real_idx == item_idx else "  "
        color = white_fg() if is_discovered else DIM
        name = item_cls.name if is_discovered else "???"
        out.append(move(start_row + i, 10) + color + prefix + name + RESET)

    # Details for the selected item on the right
    if items:
        out.extend(_detail_panel(items[item_idx], item_idx, discovered, start_row, term_w))

    # Footer
    out.append(
        move(term_h - 1, 1)
        + ansi_center(light_gray_fg() + "←/→: Category  ↑/↓: Item  Esc/Q: Back" + RESET, term_w)
    )
    return "".join(out)


def _detail_panel(
    item_cls: Any, item_idx: int, discovered: Collection[str], start_row: int, term_w: int
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


def show_collection(reader: KeyReader, profile: Profile) -> None:
    """Gallery browser for discovered items."""
    from belote.ui.fit_guard import require_minimum

    from ..items.registry import registry

    categories: list[tuple[str, list[Any]]] = [
        ("Jokers", list(registry.jokers.values())),
        ("Tarots", list(registry.tarots.values())),
        ("Planets", list(registry.planets.values())),
        ("Vouchers", list(registry.vouchers.values())),
    ]
    cat_idx = 0
    item_idx = 0
    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        items = categories[cat_idx][1]
        item_idx = min(item_idx, len(items) - 1) if items else 0
        sys.stdout.write(
            collection_frame(
                categories, profile.discovered_items, cat_idx, item_idx, term_w, term_h
            )
        )
        sys.stdout.flush()
        invalidate_diff()

        event = reader.read()
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
