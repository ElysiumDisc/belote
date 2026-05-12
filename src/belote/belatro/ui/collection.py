from __future__ import annotations

import sys
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
from belote.ui.render import get_term_size

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..progression.save import Profile


def show_collection(reader: KeyReader, profile: Profile) -> None:
    """Gallery browser for discovered items."""
    from ..items.registry import registry

    # Categorize all items
    categories: list[tuple[str, list[Any]]] = [
        ("Jokers", list(registry.jokers.values())),
        ("Tarots", list(registry.tarots.values())),
        ("Planets", list(registry.planets.values())),
        ("Vouchers", list(registry.vouchers.values())),
    ]

    cat_idx = 0
    item_idx = 0

    while True:
        term_w, term_h = get_term_size()
        cat_name, items = categories[cat_idx]
        item_idx = min(item_idx, len(items) - 1) if items else 0

        out = [clear_screen(), hide_cursor()]

        # Header
        title = f"COLLECTION - {cat_name} ({len(profile.discovered_items)} Discovered)"
        out.append(move(2, 1) + ansi_center(gold_fg() + BOLD + title + RESET, term_w))
        out.append(
            move(3, 1) + ansi_center(menu_border_fg() + "─" * (len(title) + 4) + RESET, term_w)
        )

        # Category Tabs
        cat_line = []
        for i, (name, _) in enumerate(categories):
            label = f"[{name}]" if i == cat_idx else f" {name} "
            color = gold_fg() + BOLD if i == cat_idx else white_fg()
            cat_line.append(color + label + RESET)
        out.append(move(5, 1) + ansi_center("  ".join(cat_line), term_w))

        # Item Grid (simple list for now)
        start_row = 7
        max_rows = term_h - 12
        visible_items = items[item_idx : item_idx + max_rows] if items else []

        for i, item_cls in enumerate(visible_items):
            row = start_row + i
            real_idx = item_idx + i
            is_discovered = item_cls.id in profile.discovered_items

            prefix = "> " if real_idx == item_idx else "  "
            color = white_fg() if is_discovered else DIM
            name = item_cls.name if is_discovered else "???"

            text = f"{prefix}{name}"
            out.append(move(row, 10) + color + text + RESET)

            # Show details for discovered item on the right
            if real_idx == item_idx:
                info_col = 40
                if is_discovered:
                    out.append(move(start_row, info_col) + gold_fg() + BOLD + item_cls.name + RESET)
                    out.append(move(start_row + 1, info_col) + menu_border_fg() + "─" * 30 + RESET)

                    # Try to show ASCII art if available
                    art = getattr(item_cls, "ascii_art", [])
                    for j, art_line in enumerate(art):
                        out.append(
                            move(start_row + 2 + j, info_col) + menu_art_fg() + art_line + RESET
                        )

                    desc_start = start_row + 2 + (len(art) if art else 0) + 1
                    desc = getattr(item_cls, "description", "No description.")
                    words = desc.split()
                    line = ""
                    r = desc_start
                    for w in words:
                        if len(line) + len(w) + 1 > 40:
                            out.append(move(r, info_col) + white_fg() + line + RESET)
                            line = w
                            r += 1
                        else:
                            line = (line + " " + w).strip()
                    if line:
                        out.append(move(r, info_col) + white_fg() + line + RESET)
                else:
                    out.append(move(start_row, info_col) + DIM + "??? (Undiscovered)" + RESET)
                    out.append(
                        move(start_row + 2, info_col)
                        + DIM
                        + "Keep playing to find this item!"
                        + RESET
                    )

        # Footer
        out.append(
            move(term_h - 1, 1)
            + ansi_center(light_gray_fg() + "←/→: Category  ↑/↓: Item  Esc/Q: Back" + RESET, term_w)
        )

        sys.stdout.write("".join(out))
        sys.stdout.flush()

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
