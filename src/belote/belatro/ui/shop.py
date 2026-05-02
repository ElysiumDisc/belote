from __future__ import annotations

from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    gold_fg,
    green_fg,
    menu_art_fg,
    move,
    white_fg,
)
from belote.input import Key

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..run.shop import Shop


class ShopScreen:
    """The interactive shop UI."""

    def __init__(self, shop: Shop, reader: KeyReader) -> None:
        self.shop = shop
        self.reader = reader
        self.selected = 0

    def run(self) -> None:
        """Main shop loop."""
        self.shop.generate_inventory()
        self._render()
        while True:
            event = self.reader.read()
            key = event.key
            num_items = len(self.shop.inventory)
            total_options = num_items + 1  # items + reroll
            if key == Key.LEFT:
                self.selected = (self.selected - 1) % total_options
            elif key == Key.RIGHT:
                self.selected = (self.selected + 1) % total_options
            elif key == Key.ENTER:
                if self.selected < num_items:
                    self.shop.buy_item(self.selected)
                    if self.selected >= len(self.shop.inventory):
                        self.selected = max(0, len(self.shop.inventory) - 1)
                else:
                    self.shop.reroll()
                    self.selected = min(self.selected, len(self.shop.inventory))
            elif key in (Key.ESC, Key.QUIT):
                break
            self._render()

    def _card_col(self, i: int, num_items: int) -> int:
        spacing = max(18, (80 - 2) // (num_items + 1))
        return 2 + i * spacing

    def _render_planet_card(self, item: object, row: int, col: int, is_sel: bool) -> None:
        from belote.ansi import move

        bc = REVERSE if is_sel else ""
        ac = RESET
        lv = getattr(item, "level", 0)
        art = getattr(item, "ascii_art", ("", "", ""))
        shop_lines = getattr(item, "shop_lines", ("              ", "              "))
        level_inner = f"  Lv.{lv} → {lv + 1}"
        print(move(row, col) + bc + "╔══════════════╗" + ac)
        for i, art_line in enumerate(art):
            print(move(row + 1 + i, col) + bc + f"│{menu_art_fg()}{art_line:<14}{RESET}{bc}│" + ac)
        print(
            move(row + 1 + len(art), col) + bc + f"│{white_fg()}{level_inner:<14}{RESET}{bc}│" + ac
        )
        for i, sl in enumerate(shop_lines):
            print(
                move(row + 2 + len(art) + i, col) + bc + f"│{white_fg()}{sl:<14}{RESET}{bc}│" + ac
            )
        cost = getattr(item, "cost", 0)
        print(
            move(row + 2 + len(art) + len(shop_lines), col)
            + bc
            + f"╚══════════════╝ {gold_fg()}${cost}{RESET}"
            + ac
        )

    def _render_item_card(self, item: object, row: int, col: int, is_sel: bool) -> None:
        bc = REVERSE if is_sel else ""
        ac = RESET
        name = getattr(item, "name", "?")
        cost = getattr(item, "cost", 0)
        print(move(row, col) + bc + "┌────────────────┐" + ac)
        print(move(row + 1, col) + bc + f"│{gold_fg()}{name:^14}{RESET}{bc}│" + ac)
        print(move(row + 2, col) + bc + "│" + " " * 14 + "│" + ac)
        print(move(row + 3, col) + bc + f"│{white_fg()}{'$' + str(cost):^14}{RESET}{bc}│" + ac)
        print(move(row + 4, col) + bc + "└────────────────┘" + ac)

    def _render(self) -> None:
        from ..items.base import Planet

        clear_screen()
        print(move(2, 1) + ansi_center(gold_fg() + BOLD + "=== THE SHOP ===" + RESET, 80))
        print(
            move(4, 1)
            + white_fg()
            + "  Money: "
            + green_fg()
            + f"${self.shop.run.economy.money}"
            + RESET
        )

        num_items = len(self.shop.inventory)
        card_start_row = 6

        for i, item in enumerate(self.shop.inventory):
            col = self._card_col(i, num_items)
            is_sel = i == self.selected
            if isinstance(item, Planet):
                self._render_planet_card(item, card_start_row, col, is_sel)
            else:
                self._render_item_card(item, card_start_row, col, is_sel)

        # Reroll option
        reroll_idx = num_items
        reroll_col = self._card_col(reroll_idx, num_items)
        is_reroll_sel = self.selected == reroll_idx
        bc = REVERSE if is_reroll_sel else ""
        reroll_label = f"Reroll ${self.shop.reroll_cost}"
        print(move(card_start_row + 3, reroll_col) + bc + f"[ {reroll_label} ]" + RESET)

        # Selected item description
        if self.selected < num_items:
            item = self.shop.inventory[self.selected]
            desc = getattr(item, "description", "")
            print(move(18, 1) + ansi_center(white_fg() + desc[:78] + RESET, 80))

        print(
            move(20, 1)
            + ansi_center(gold_fg() + "← → Navigate   Enter: Buy   Esc: Continue" + RESET, 80)
        )
