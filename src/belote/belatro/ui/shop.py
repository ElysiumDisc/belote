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
            elif key == Key.CHAR and event.char and event.char.lower() == "c":
                # Open the consumables tray. Local import to avoid a circular
                # module load at startup (consumables imports from this UI tree).
                from .consumables import ConsumablesOverlay

                overlay = ConsumablesOverlay(self.shop.run, self.reader)
                used = overlay.open()
                if used:
                    from .announce import BelAtroAnnounce

                    BelAtroAnnounce.banner("Consumable activated.", self.reader, hold=0.8)
            elif key in (Key.ESC, Key.QUIT, Key.EOF):
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
        from belote.ui.fit_guard import require_minimum
        from belote.ui.layout import vcenter_lines
        from belote.ui.render import get_term_size

        from ..items.registry import registry

        planet_ids = list(registry.planets.keys())
        if not planet_ids:
            return None

        require_minimum(self.reader)
        term_w, term_h = get_term_size()

        lines: list[str] = []
        lines.append(ansi_center(gold_fg() + BOLD + "FORGE A PLANET" + RESET, term_w))
        lines.append("")
        lines.append(
            ansi_center(white_fg() + "Spend 3 Tierce charges to level up:" + RESET, term_w)
        )
        lines.append("")
        for i, p_id in enumerate(planet_ids):
            planet_cls = registry.get_planet(p_id)
            name = getattr(planet_cls, "name", p_id) if planet_cls else p_id
            lines.append(ansi_center(white_fg() + f"[{i + 1}] {name}" + RESET, term_w))
        lines.append("")
        lines.append(ansi_center("[1-9] pick   Esc cancel", term_w))

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()
        from belote.ui.render import invalidate_diff
        invalidate_diff()

        while True:
            event = self.reader.read()
            if event.key in (Key.ESC, Key.QUIT, Key.EOF):
                return None
            if event.key == Key.CHAR and event.char and event.char.isdigit():
                idx = int(event.char) - 1
                if 0 <= idx < len(planet_ids):
                    return planet_ids[idx]

    # Card frame width — must match the printable width of the borders in
    # _render_planet_card / _render_item_card. Don't change without re-laying
    # out the art inside.
    _CARD_W = 16

    def _card_col(self, i: int, num_items: int, term_w: int) -> int:
        """Column for the i-th *card* (not the action buttons).

        Centers the row of `num_items` cards across the terminal, tightening
        the inter-card gap as needed to avoid overflow. Cards may touch at
        narrow widths; they never overlap and the strip never overflows.
        """
        if num_items <= 0:
            return 2
        card_w = self._CARD_W
        # Try a 2-col gap by default; shrink to 0 if the strip would overflow.
        for gap in (2, 1, 0):
            strip = num_items * card_w + (num_items - 1) * gap
            if strip <= term_w - 2:
                start = max(2, (term_w - strip) // 2)
                return start + i * (card_w + gap)
        # Even with cards touching (gap=0) we overflow — clamp leftmost to 2
        # and let the strip extend right; the caller can't render this many
        # cards at this width anyway.
        return 2 + i * card_w

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
        from belote.ui.fit_guard import require_minimum
        from belote.ui.render import get_term_size

        from ..items.base import Planet

        require_minimum(self.reader)
        term_w, term_h = get_term_size()

        sys.stdout.write(clear_screen())
        sys.stdout.flush()

        # Vertical layout (centered for the planet-card worst case of 9 rows):
        #   title / blank / money / blank / cards (9) / blank / actions /
        #   blank / description / blank / hints                 → 19 rows
        # Compute top so the block sits centered in term_h.
        content_h = 19
        top = max(1, (term_h - content_h) // 2)
        title_row = top
        money_row = top + 2
        card_row = top + 4
        actions_row = top + 14  # card_row + 9 (planet height) + 1 blank
        desc_row = top + 16
        hint_row = top + 18

        print(
            move(title_row, 1)
            + ansi_center(gold_fg() + BOLD + "=== THE SHOP ===" + RESET, term_w)
        )
        print(
            move(money_row, 1)
            + ansi_center(
                white_fg() + "Money: " + green_fg() + f"${self.shop.run.economy.money}" + RESET,
                term_w,
            )
        )

        num_items = len(self.shop.inventory)

        for i, item in enumerate(self.shop.inventory):
            col = self._card_col(i, num_items, term_w)
            is_sel = i == self.selected
            if isinstance(item, Planet):
                self._render_planet_card(item, card_row, col, is_sel)
            else:
                self._render_item_card(item, card_row, col, is_sel)

        # Action buttons (reroll, forge) render on their own row BELOW the
        # cards. Pre-3.7.2 these sat inline mid-card, which overflowed 80-col
        # terminals when the forge slot appeared. Centering the action strip
        # avoids that regardless of slot count.
        reroll_idx = num_items
        forge_idx = num_items + 1 if self._forge_available() else -1
        reroll_label = f"[ Reroll ${self.shop.reroll_cost} ]"
        forge_label = (
            f"[ Forge x{self.shop.run.tierce_charges}/3 ]" if forge_idx >= 0 else ""
        )
        actions: list[tuple[int, str, bool]] = [
            (reroll_idx, reroll_label, self.selected == reroll_idx),
        ]
        if forge_idx >= 0:
            actions.append((forge_idx, forge_label, self.selected == forge_idx))

        # Center the action strip: total width = sum(label widths) + 4-col gaps.
        gap = 4
        labels_w = sum(len(lbl) for _, lbl, _ in actions) + gap * (len(actions) - 1)
        start_col = max(2, (term_w - labels_w) // 2)
        cursor = start_col
        for _, lbl, sel in actions:
            bc = REVERSE if sel else ""
            print(move(actions_row, cursor) + bc + lbl + RESET)
            cursor += len(lbl) + gap

        # Selected item description
        if self.selected < num_items:
            item = self.shop.inventory[self.selected]
            desc = getattr(item, "description", "")
            print(move(desc_row, 1) + ansi_center(white_fg() + desc[: term_w - 2] + RESET, term_w))
        elif forge_idx >= 0 and self.selected == forge_idx:
            print(
                move(desc_row, 1)
                + ansi_center(
                    white_fg() + "Spend 3 Tierce charges to level up a Planet contract."
                    + RESET,
                    term_w,
                )
            )

        consumable_count = len(self.shop.run.consumables)
        hint = (
            f"← → Navigate   Enter: Buy   C: Consumables ({consumable_count})   Esc: Continue"
        )
        print(move(hint_row, 1) + ansi_center(gold_fg() + hint + RESET, term_w))
        from belote.ui.render import invalidate_diff
        invalidate_diff()
