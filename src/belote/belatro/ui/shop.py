from __future__ import annotations

import sys
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

    def _forge_available(self) -> bool:
        """The Forge action only appears when the player owns the TierceForge
        voucher and has accumulated 3 charges to spend."""
        from ..items.vouchers import TierceForge

        return (
            any(isinstance(v, TierceForge) for v in self.shop.run.vouchers)
            and self.shop.run.tierce_charges >= 3
        )

    def run(self) -> None:
        """Main shop loop."""
        self.shop.generate_inventory()
        self._render()
        while True:
            event = self.reader.read()
            key = event.key
            num_items = len(self.shop.inventory)
            forge_idx = num_items + 1 if self._forge_available() else -1
            total_options = num_items + 1 + (1 if forge_idx >= 0 else 0)
            if key == Key.LEFT:
                self.selected = (self.selected - 1) % total_options
            elif key == Key.RIGHT:
                self.selected = (self.selected + 1) % total_options
            elif key == Key.ENTER:
                if self.selected < num_items:
                    bought = self.shop.buy_item(self.selected)
                    if not bought and self.shop.last_buy_failure == "slots_full":
                        from .announce import BelAtroAnnounce

                        BelAtroAnnounce.banner(
                            "Slots full — sell first to make room", self.reader, hold=1.0
                        )
                    if self.selected >= len(self.shop.inventory):
                        self.selected = max(0, len(self.shop.inventory) - 1)
                elif self.selected == num_items:
                    self.shop.reroll()
                    # Clamp to a *valid* index: len(inventory)-1, not len.
                    # The previous form let `selected == len(inventory)` slip
                    # through, OOB on the next render's inventory[self.selected].
                    self.selected = min(self.selected, max(0, len(self.shop.inventory) - 1))
                elif self.selected == forge_idx:
                    self._handle_forge()
            elif key in (Key.ESC, Key.QUIT):
                break
            self._render()

    def _handle_forge(self) -> None:
        """Spend 3 Tierce charges on a player-picked Planet contract level-up."""
        from ..items.registry import registry
        from ..items.vouchers import forge_tierce

        planet_id = self._pick_planet()
        if planet_id is None:
            return
        if forge_tierce(self.shop.run, planet_id):
            planet_cls = registry.get_planet(planet_id)
            label = getattr(planet_cls, "name", planet_id) if planet_cls else planet_id
            from .announce import BelAtroAnnounce

            BelAtroAnnounce.banner(f"Forged: {label} levelled up!", self.reader, hold=1.0)

    def _pick_planet(self) -> str | None:
        """Numbered overlay to pick a planet contract. Returns the chosen
        planet id, or None if the player cancelled."""
        from belote.ui.render import get_term_size

        from ..items.registry import registry

        planet_ids = list(registry.planets.keys())
        if not planet_ids:
            return None

        term_w, _ = get_term_size()
        sys.stdout.write(clear_screen())
        print(move(2, 1) + ansi_center(gold_fg() + BOLD + "FORGE A PLANET" + RESET, term_w))
        print(
            move(4, 1)
            + ansi_center(white_fg() + "Spend 3 Tierce charges to level up:" + RESET, term_w)
        )
        for i, p_id in enumerate(planet_ids):
            planet_cls = registry.get_planet(p_id)
            name = getattr(planet_cls, "name", p_id) if planet_cls else p_id
            print(move(6 + i, 4) + white_fg() + f"  [{i + 1}] {name}" + RESET)
        hint_row = 6 + len(planet_ids) + 2
        print(move(hint_row, 1) + ansi_center("[1-9] pick   Esc cancel", term_w))
        sys.stdout.flush()

        while True:
            event = self.reader.read()
            if event.key in (Key.ESC, Key.QUIT):
                return None
            if event.key == Key.CHAR and event.char and event.char.isdigit():
                idx = int(event.char) - 1
                if 0 <= idx < len(planet_ids):
                    return planet_ids[idx]

    def _card_col(self, i: int, num_items: int, term_w: int) -> int:
        spacing = max(18, (term_w - 2) // (num_items + 1))
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
        from belote.ui.render import get_term_size

        from ..items.base import Planet

        term_w, term_h = get_term_size()

        sys.stdout.write(clear_screen())
        sys.stdout.flush()

        print(move(1, 1) + ansi_center(gold_fg() + BOLD + "=== THE SHOP ===" + RESET, term_w))
        print(
            move(3, 1)
            + white_fg()
            + "  Money: "
            + green_fg()
            + f"${self.shop.run.economy.money}"
            + RESET
        )

        num_items = len(self.shop.inventory)
        card_start_row = 5

        for i, item in enumerate(self.shop.inventory):
            col = self._card_col(i, num_items, term_w)
            is_sel = i == self.selected
            if isinstance(item, Planet):
                self._render_planet_card(item, card_start_row, col, is_sel)
            else:
                self._render_item_card(item, card_start_row, col, is_sel)

        # Reroll option
        reroll_idx = num_items
        reroll_col = self._card_col(reroll_idx, num_items, term_w)
        is_reroll_sel = self.selected == reroll_idx
        bc = REVERSE if is_reroll_sel else ""
        reroll_label = f"Reroll ${self.shop.reroll_cost}"
        print(move(card_start_row + 3, reroll_col) + bc + f"[ {reroll_label} ]" + RESET)

        # Forge option (only when TierceForge voucher owned + 3 charges available)
        forge_idx = num_items + 1 if self._forge_available() else -1
        if forge_idx >= 0:
            forge_col = self._card_col(forge_idx, num_items, term_w)
            is_forge_sel = self.selected == forge_idx
            fc = REVERSE if is_forge_sel else ""
            forge_label = f"Forge x{self.shop.run.tierce_charges}/3"
            print(move(card_start_row + 3, forge_col) + fc + f"[ {forge_label} ]" + RESET)

        # Selected item description
        if self.selected < num_items:
            item = self.shop.inventory[self.selected]
            desc = getattr(item, "description", "")
            print(move(18, 1) + ansi_center(white_fg() + desc[: term_w - 2] + RESET, term_w))
        elif self.selected == num_items + 1 and forge_idx >= 0:
            print(
                move(18, 1)
                + ansi_center(
                    white_fg() + "Spend 3 Tierce charges to level up a Planet contract."
                    + RESET,
                    term_w,
                )
            )

        print(
            move(20, 1)
            + ansi_center(gold_fg() + "← → Navigate   Enter: Buy   Esc: Continue" + RESET, term_w)
        )
