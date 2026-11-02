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
    red_fg,
    white_fg,
)
from belote.input import Key, typed

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..run.shop import Shop


# Shop description prefix per joker edition (values of items.base.Edition).
_EDITION_LABELS: dict[str, str] = {
    "foil": "Foil: +50 chips per trigger",
    "holo": "Holo: +10 Mult per trigger",
    "poly": "Polychrome: x1.5 Mult per trigger",
    "neg": "Negative: +1 joker slot",
}


class ShopScreen:
    """The interactive shop UI."""

    def __init__(self, shop: Shop, reader: KeyReader) -> None:
        self.shop = shop
        self.reader = reader
        self.selected = 0
        self.spent_medals: list[str] = []

    def _forge_available(self) -> bool:
        """The Forge action only appears when the player owns the TierceForge
        voucher and has accumulated 3 charges to spend."""
        from ..items.vouchers import TierceForge

        return (
            any(isinstance(v, TierceForge) for v in self.shop.run.vouchers)
            and self.shop.run.tierce_charges >= 3
        )

    def _actions(self) -> list[str]:
        """Action buttons after the item cards, in order (5.0.0: Fuse when Le
        Serment has something to fuse). Skipping the next blind is the K
        hotkey, advertised on the status line."""
        from ..run import usurier

        actions = ["reroll"]
        if self._forge_available():
            actions.append("forge")
        if self.shop.available_fusions():
            actions.append("fuse")
        # 5.0.0 L'Usurier: his loan when he visits; Repay while you owe him.
        if self.shop.run.loan_debt > 0:
            actions.append("repay")
        elif usurier.can_borrow(self.shop.run):
            actions.append("loan")
        return actions

    def run(self) -> None:
        """Main shop loop."""
        # 5.0.0: waiting Médailles bend this shop's first roll.
        self.spent_medals = [m.name for m in self.shop.spend_medals()]
        self.shop.generate_inventory()
        self._render()
        while True:
            event = self.reader.read()
            key = event.key
            num_items = len(self.shop.inventory)
            actions = self._actions()
            total_options = num_items + len(actions)
            if key == Key.LEFT:
                self.selected = (self.selected - 1) % total_options
            elif key == Key.RIGHT:
                self.selected = (self.selected + 1) % total_options
            elif key == Key.ENTER:
                self._activate(num_items, actions)
            elif key == Key.MOUSE:
                # 5.0.0: click an offer / button to select it, click it again
                # to buy / press it (the keyboard's ← → then Enter).
                target = self._clicked(event.pos, num_items)
                if target is not None:
                    if target == self.selected:
                        self._activate(num_items, actions)
                    else:
                        self.selected = target
            elif typed(event, "k"):
                # 5.0.0 Médailles: skip the next blind for its medal.
                if self._handle_skip():
                    break
            elif key == Key.CHAR and event.char and event.char.lower() == "c":
                # Open the consumables tray. Local import to avoid a circular
                # module load at startup (consumables imports from this UI tree).
                from .consumables import ConsumablesOverlay

                overlay = ConsumablesOverlay(self.shop.run, self.reader)
                used = overlay.open()
                # 4.11.0: surface the tarot's own message (Le Juge's reroll,
                # or why it refused) instead of a generic line.
                message = self.shop.run.last_tarot_message
                if used or message:
                    from .announce import BelAtroAnnounce

                    BelAtroAnnounce.banner(
                        message or "Consumable activated.", self.reader, hold=1.2
                    )
            elif typed(event, "s"):  # S is also the DOWN alias
                self._handle_sell()
                self._clamp_selection()
            elif key in (Key.ESC, Key.QUIT, Key.EOF):
                break
            self._render()

    def _activate(self, num_items: int, actions: list[str]) -> None:
        """Enter on the current selection: buy the offer or press the button."""
        if self.selected < num_items:
            self._handle_buy(num_items)
        else:
            action = actions[min(self.selected - num_items, len(actions) - 1)]
            if action == "reroll":
                self._animate_reroll(num_items)
                self.shop.reroll()
            elif action == "forge":
                self._handle_forge()
            elif action == "fuse":
                self._handle_fuse()
            elif action in ("loan", "repay"):
                self._handle_usurier(action)
        self._clamp_selection()

    def _handle_usurier(self, action: str) -> None:
        """5.0.0: take L'Usurier's loan, or repay what you can."""
        from ..run import usurier
        from .announce import BelAtroAnnounce

        run = self.shop.run
        if action == "loan":
            if BelAtroAnnounce.yes_no(
                f"L'Usurier: borrow ${usurier.LOAN_AMOUNT} at "
                f"{int(usurier.INTEREST * 100)}% per ante, compounding? "
                f"(Owe ${usurier.SEIZE_AT}+ and he seizes your money, then jokers.)",
                self.reader,
            ) and usurier.borrow(run):
                BelAtroAnnounce.banner(
                    f"+${usurier.LOAN_AMOUNT} — L'Usurier will be back for it.",
                    self.reader,
                    hold=1.2,
                )
            return
        paid = usurier.repay(run)
        if paid:
            left = f" (${run.loan_debt} still owed)" if run.loan_debt else " — debt cleared!"
            BelAtroAnnounce.banner(f"Repaid ${paid}{left}", self.reader, hold=1.2)
        else:
            BelAtroAnnounce.banner("No money to repay with", self.reader, hold=1.0)

    @staticmethod
    def _clicked(pos: tuple[int, int] | None, num_items: int) -> int | None:
        """Selection index of the offer / button under a click, or None."""
        from belote.ui import hitmap

        target = hitmap.hit("shop", pos)
        if not isinstance(target, tuple):
            return None
        kind, index = target
        return int(index) if kind == "item" else num_items + int(index)

    def _clamp_selection(self) -> None:
        """Keep the cursor on a real option after the item / action lists
        changed (a purchase, a reroll, a fusion)."""
        total = len(self.shop.inventory) + len(self._actions())
        self.selected = max(0, min(self.selected, total - 1))

    def _handle_buy(self, num_items: int) -> None:
        from .announce import BelAtroAnnounce

        # 4.8.0: capture pre-purchase context for the animation.
        money_before = self.shop.run.economy.money
        sel_idx = self.selected
        bought = self.shop.buy_item(self.selected)
        if not bought and self.shop.last_buy_failure == "slots_full":
            BelAtroAnnounce.banner("Slots full — press S to sell a joker", self.reader, hold=1.0)
        elif bought:
            money_after = self.shop.run.economy.money
            self._animate_purchase(sel_idx, num_items, money_before, money_after)
            # 5.0.0 Le Serment: a third copy makes the oath possible.
            if any(f.kind == "oath" for f in self.shop.available_fusions()):
                BelAtroAnnounce.banner(
                    "Three copies! Le Serment can fuse them — choose Fuse.", self.reader, hold=1.5
                )
        if self.selected >= len(self.shop.inventory):
            self.selected = max(0, len(self.shop.inventory) - 1)

    def _handle_fuse(self) -> None:
        """5.0.0 Le Serment: pick a fusion (recipe or three-copy oath)."""
        from .announce import BelAtroAnnounce

        fusions = self.shop.available_fusions()
        if not fusions:
            return
        idx = self._pick_from(
            "LE SERMENT — FUSE JOKERS",
            "The inputs are consumed; the result takes the first one's slot.",
            [f.label for f in fusions],
        )
        if idx is None:
            return
        joker = self.shop.fuse(fusions[idx])
        if joker is not None:
            BelAtroAnnounce.banner(f"Le Serment: {joker.display_name}!", self.reader, hold=1.5)

    def _handle_skip(self) -> bool:
        """5.0.0 Médailles: skip the next blind? True = leave the shop now."""
        from .announce import BelAtroAnnounce

        medal = self.shop.skip_offer()
        if medal is None:
            return False
        if not BelAtroAnnounce.yes_no(
            f"Skip the next blind (no round, no payout, no shop) for {medal.name}: "
            f"{medal.description}?",
            self.reader,
        ):
            return False
        self.shop.skip_next = True
        self.shop.skip_medal = medal.id
        return True

    def _handle_sell(self) -> None:
        """Numbered overlay: pick an owned joker to sell for half its cost."""
        from belote.ui.fit_guard import require_minimum
        from belote.ui.layout import vcenter_lines
        from belote.ui.render import get_term_size, invalidate_diff

        from .announce import BelAtroAnnounce

        jokers = self.shop.run.jokers
        if not jokers:
            BelAtroAnnounce.banner("No jokers to sell", self.reader, hold=0.8)
            return

        require_minimum(self.reader)
        term_w, term_h = get_term_size()
        lines: list[str] = [
            ansi_center(gold_fg() + BOLD + "SELL A JOKER" + RESET, term_w),
            "",
        ]
        for i, joker in enumerate(jokers[:9]):
            name = getattr(joker, "name", "?")
            if self.shop.can_sell(i):
                label = f"[{i + 1}] {name}  +${self.shop.sell_value(joker)}"
            else:
                label = f"[{i + 1}] {name}  (corrupted — can't sell)"
            lines.append(ansi_center(white_fg() + label + RESET, term_w))
        lines += ["", ansi_center("[1-9] sell   Esc cancel", term_w)]
        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()
        invalidate_diff()

        while True:
            event = self.reader.read()
            if event.key in (Key.ESC, Key.QUIT, Key.EOF):
                return
            if event.key == Key.CHAR and event.char and event.char.isdigit():
                idx = int(event.char) - 1
                if not (0 <= idx < min(len(jokers), 9)):
                    continue
                name = getattr(jokers[idx], "name", "?")
                if not self.shop.can_sell(idx):
                    BelAtroAnnounce.banner(
                        f"{name} is corrupted — can't sell", self.reader, hold=1.0
                    )
                    return
                gained = self.shop.sell_joker(idx)
                BelAtroAnnounce.banner(f"Sold {name} for ${gained}", self.reader, hold=0.8)
                return

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
        from ..items.registry import registry

        planet_ids = list(registry.planets.keys())
        if not planet_ids:
            return None
        names = []
        for p_id in planet_ids:
            planet_cls = registry.get_planet(p_id)
            names.append(getattr(planet_cls, "name", p_id) if planet_cls else p_id)
        idx = self._pick_from("FORGE A PLANET", "Spend 3 Tierce charges to level up:", names)
        return None if idx is None else planet_ids[idx]

    def _pick_from(self, title: str, subtitle: str, labels: list[str]) -> int | None:
        """Numbered overlay (up to 9 entries). Returns the picked index, or
        None if the player cancelled."""
        from belote.ui.fit_guard import require_minimum
        from belote.ui.layout import vcenter_lines
        from belote.ui.render import get_term_size, invalidate_diff

        labels = labels[:9]
        require_minimum(self.reader)
        term_w, term_h = get_term_size()
        lines: list[str] = [
            ansi_center(gold_fg() + BOLD + title + RESET, term_w),
            "",
            ansi_center(white_fg() + subtitle + RESET, term_w),
            "",
        ]
        for i, label in enumerate(labels):
            text = f"[{i + 1}] {label}"[: term_w - 2]
            lines.append(ansi_center(white_fg() + text + RESET, term_w))
        lines += ["", ansi_center("[1-9] pick   Esc cancel", term_w)]
        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()
        invalidate_diff()

        while True:
            event = self.reader.read()
            if event.key in (Key.ESC, Key.QUIT, Key.EOF):
                return None
            if event.key == Key.CHAR and event.char and event.char.isdigit():
                idx = int(event.char) - 1
                if 0 <= idx < len(labels):
                    return idx

    # Card frame width — must match the printable width of the borders in
    # _render_planet_card / _render_item_card. Don't change without re-laying
    # out the art inside.
    _CARD_W = 16
    # Vertical block: title / money / status / cards (9) / actions /
    # description / hints, with blank separators → 20 rows.
    _CONTENT_H = 20

    def _rows(self, term_h: int) -> dict[str, int]:
        top = max(1, (term_h - self._CONTENT_H) // 2)
        return {
            "title": top,
            "money": top + 2,
            "status": top + 3,
            "cards": top + 5,
            "actions": top + 15,  # cards + 9 (planet height) + 1 blank
            "desc": top + 17,
            "hint": top + 19,
        }

    def _window(self, num_items: int, term_w: int) -> tuple[int, int]:
        """(first, count) of the cards shown. 5.0.0: a shop can now hold more
        cards than fit (the Atelier offer, L'Épicier's extra jokers, Le
        Téléphone), so the strip scrolls to keep the selection on screen."""
        fit = max(1, (term_w - 2) // self._CARD_W)
        if num_items <= fit:
            return 0, num_items
        sel = min(self.selected, num_items - 1)
        first = max(0, min(sel - fit + 1, num_items - fit))
        if sel < first:
            first = sel
        return first, fit

    def _card_col(self, i: int, num_items: int, term_w: int) -> int:
        """Column for the i-th *card* (not the action buttons), or -1 when it
        is scrolled out of view.

        Centers the visible cards across the terminal, tightening the gap as
        needed; cards may touch at narrow widths but never overlap or overflow.
        """
        first, count = self._window(num_items, term_w)
        if not first <= i < first + count:
            return -1
        card_w = self._CARD_W
        slot = i - first
        for gap in (2, 1, 0):
            strip = count * card_w + (count - 1) * gap
            if strip <= term_w - 2:
                start = max(2, (term_w - strip) // 2)
                return start + slot * (card_w + gap)
        return 2 + slot * card_w

    def _render_planet_card(self, item: object, row: int, col: int, is_sel: bool) -> list[str]:
        bc = REVERSE if is_sel else ""
        ac = RESET
        lv = getattr(item, "level", 0)
        art = getattr(item, "ascii_art", ("", "", ""))
        shop_lines = getattr(item, "shop_lines", ("              ", "              "))
        level_inner = f"  Lv.{lv} → {lv + 1}"
        parts: list[str] = [move(row, col) + bc + "╔══════════════╗" + ac + "\n"]
        for i, art_line in enumerate(art):
            parts.append(
                move(row + 1 + i, col)
                + bc
                + f"│{menu_art_fg()}{art_line:<14}{RESET}{bc}│"
                + ac
                + "\n"
            )
        parts.append(
            move(row + 1 + len(art), col)
            + bc
            + f"│{white_fg()}{level_inner:<14}{RESET}{bc}│"
            + ac
            + "\n"
        )
        for i, sl in enumerate(shop_lines):
            parts.append(
                move(row + 2 + len(art) + i, col)
                + bc
                + f"│{white_fg()}{sl:<14}{RESET}{bc}│"
                + ac
                + "\n"
            )
        cost = getattr(item, "cost", 0)
        parts.append(
            move(row + 2 + len(art) + len(shop_lines), col)
            + bc
            + f"╚══════════════╝ {gold_fg()}${cost}{RESET}"
            + ac
            + "\n"
        )
        return parts

    def _owned_copies(self, item: object) -> int:
        item_id = getattr(item, "id", None)
        return sum(1 for j in self.shop.run.jokers if j.id == item_id)

    def _render_item_card(self, item: object, row: int, col: int, is_sel: bool) -> list[str]:
        from ..core.card_mods import CardModOffer

        bc = REVERSE if is_sel else ""
        ac = RESET
        # Frame is _CARD_W (16) cells: 14 inner + 2 borders. Names longer than
        # 14 cells used to overflow the frame into the neighbouring card.
        name = str(getattr(item, "name", "?"))[:14]
        cost = getattr(item, "cost", 0)
        # The blank row carries a tag: 4.11.0 Le Téléphone partner offers;
        # 5.0.0 the Atelier offer's card, and how many copies of an offered
        # joker you already own (Le Serment wants three).
        if isinstance(item, CardModOffer):
            tag = f"on {item.card!r}"
        elif getattr(item, "for_partner", False):
            tag = "for partner"
        else:
            owned = self._owned_copies(item)
            tag = f"you own {owned}" if owned else ""
        price = "free" if cost == 0 else "$" + str(cost)
        return [
            move(row, col) + bc + "┌──────────────┐" + ac + "\n",
            move(row + 1, col) + bc + f"│{gold_fg()}{name:^14}{RESET}{bc}│" + ac + "\n",
            move(row + 2, col) + bc + f"│{green_fg()}{tag:^14}{RESET}{bc}│" + ac + "\n",
            move(row + 3, col) + bc + f"│{white_fg()}{price:^14}{RESET}{bc}│" + ac + "\n",
            move(row + 4, col) + bc + "└──────────────┘" + ac + "\n",
        ]

    def _status_line(self) -> str:
        """5.0.0: medals spent on this shop, else a preview of the next blind
        (its target and any Contrat Capot / Grand Chelem on offer)."""
        from ..run.contracts import CONTRACTS, contract_for
        from ..run.medals import upcoming_blind

        spent = getattr(self, "spent_medals", [])
        if spent:
            return "Médailles: " + ", ".join(spent)
        run = self.shop.run
        ante, offset, blind = upcoming_blind(run)
        label = ("Small", "Big", "Boss")[blind]
        text = f"Next: Ante {ante} · {label} Blind"
        kind = contract_for(run, ante, offset, blind)
        if kind is not None:
            text += f" · {CONTRACTS[kind].name} on offer"
        pending = len(run.medals)
        if pending:
            text += f" · {pending} Médaille(s) waiting"
        medal = self.shop.skip_offer()
        if medal is not None:
            text += f" · K: skip it for {medal.name}"
        return text

    def _action_label(self, action: str) -> str:
        if action == "reroll":
            return (
                "[ Reroll free ]"
                if self.shop.reroll_cost == 0
                else (f"[ Reroll ${self.shop.reroll_cost} ]")
            )
        if action == "forge":
            return f"[ Forge x{self.shop.run.tierce_charges}/3 ]"
        if action == "loan":
            from ..run.usurier import LOAN_AMOUNT

            return f"[ Loan ${LOAN_AMOUNT} ]"
        if action == "repay":
            run = self.shop.run
            return f"[ Repay ${min(run.loan_debt, run.economy.money)} ]"
        return f"[ Fuse x{len(self.shop.available_fusions())} ]"

    def _action_description(self, action: str) -> str:
        if action == "forge":
            return "Spend 3 Tierce charges to level up a Planet contract."
        if action == "fuse":
            return "Le Serment: fuse a recipe pair, or three copies of a joker into a Juré (✦)."
        if action == "loan":
            return (
                "L'Usurier lends $30 at 20% per ante, compounding. Repay any time; owe $90 "
                "and he seizes your money, then your jokers."
            )
        if action == "repay":
            return (
                f"You owe L'Usurier ${self.shop.run.loan_debt} (+20% each ante). "
                "Pay back as much as you can."
            )
        return ""

    def _render(self) -> None:
        from belote.ui.fit_guard import require_minimum
        from belote.ui.render import get_term_size, invalidate_diff

        from ..items.base import Planet

        require_minimum(self.reader)
        term_w, term_h = get_term_size()
        rows = self._rows(term_h)

        # Accumulate the entire frame into one buffer so it lands as a single
        # `sys.stdout.write` + `flush`. Same batched-write convention as
        # `belatro/ui/hud.py::_render` and `prompts.py::show_help`.
        parts: list[str] = [clear_screen()]
        parts.append(
            move(rows["title"], 1)
            + ansi_center(gold_fg() + BOLD + "=== THE SHOP ===" + RESET, term_w)
            + "\n"
        )
        debt = self.shop.run.loan_debt
        owed = f"{white_fg()}   Debt: {red_fg()}${debt}" if debt else ""
        parts.append(
            move(rows["money"], 1)
            + ansi_center(
                white_fg()
                + "Money: "
                + green_fg()
                + f"${self.shop.run.economy.money}"
                + owed
                + RESET,
                term_w,
            )
            + "\n"
        )
        parts.append(
            move(rows["status"], 1)
            + ansi_center(menu_art_fg() + self._status_line()[: term_w - 2] + RESET, term_w)
            + "\n"
        )

        from belote.ui import hitmap

        num_items = len(self.shop.inventory)
        first, count = self._window(num_items, term_w)
        regions: list[hitmap.Region] = []
        for i, item in enumerate(self.shop.inventory):
            col = self._card_col(i, num_items, term_w)
            if col < 0:
                continue
            is_sel = i == self.selected
            if isinstance(item, Planet):
                card = self._render_planet_card(item, rows["cards"], col, is_sel)
            else:
                card = self._render_item_card(item, rows["cards"], col, is_sel)
            parts.extend(card)
            regions.append(hitmap.Region(rows["cards"], col, len(card), self._CARD_W, ("item", i)))
        # Scroll hints when cards are out of view.
        if first > 0:
            parts.append(move(rows["cards"] + 2, 1) + gold_fg() + "‹" + RESET)
        if first + count < num_items:
            parts.append(move(rows["cards"] + 2, term_w) + gold_fg() + "›" + RESET)

        # Action buttons render on their own row BELOW the cards, centered.
        actions = self._actions()
        labels = [self._action_label(a) for a in actions]
        gap = 3
        labels_w = sum(len(lbl) for lbl in labels) + gap * (len(labels) - 1)
        cursor = max(2, (term_w - labels_w) // 2)
        for j, lbl in enumerate(labels):
            bc = REVERSE if self.selected == num_items + j else ""
            parts.append(move(rows["actions"], cursor) + bc + lbl + RESET + "\n")
            regions.append(hitmap.Region(rows["actions"], cursor, 1, len(lbl), ("action", j)))
            cursor += len(lbl) + gap
        hitmap.set_regions("shop", regions)

        # Selected item / action description
        desc = ""
        if self.selected < num_items:
            item = self.shop.inventory[self.selected]
            desc = getattr(item, "description", "")
            # Editions raise the price 1.5x but weren't shown anywhere, so the
            # player couldn't see why a joker cost more or spot a Negative one.
            ed_label = _EDITION_LABELS.get(getattr(getattr(item, "edition", None), "value", ""))
            if ed_label:
                desc = f"[{ed_label}] {desc}"
            if getattr(item, "for_partner", False):
                desc = f"[Partner slot] {desc}"
        elif self.selected - num_items < len(actions):
            desc = self._action_description(actions[self.selected - num_items])
        if desc:
            parts.append(
                move(rows["desc"], 1)
                + ansi_center(white_fg() + desc[: term_w - 2] + RESET, term_w)
                + "\n"
            )

        consumable_count = len(self.shop.run.consumables)
        hint = (
            f"← → Navigate   Enter: Buy   S: Sell   C: Consumables ({consumable_count})   "
            "Esc: Continue"
        )
        parts.append(
            move(rows["hint"], 1)
            + ansi_center(gold_fg() + hint[: term_w - 2] + RESET, term_w)
            + "\n"
        )

        sys.stdout.write("".join(parts))
        sys.stdout.flush()
        invalidate_diff()

    # ── 4.8.0 / B2: purchase + reroll feedback ────────────────────────────

    def _animate_purchase(
        self,
        sel_idx: int,
        num_items_before: int,
        money_before: int,
        money_after: int,
    ) -> None:
        """Pulse the bought card slot in gold, then tick down the money figure.

        Both effects run BEFORE the next `_render()` repaints the shop, so
        they animate on the still-on-screen pre-purchase frame. Honours
        `BELOTE_NO_ANIM` via the underlying anim helpers.
        """
        from belote.ui.anim import animations_enabled, pulse_text, tick_bar
        from belote.ui.render import get_term_size

        if not animations_enabled():
            return

        term_w, term_h = get_term_size()
        rows = self._rows(term_h)
        card_row, money_row = rows["cards"], rows["money"]

        # Pulse a 16-cell wide gold band across the card's top border. We
        # paint on the same row the card frame currently occupies; the
        # following `_render()` will fully repaint the area.
        col = max(2, self._card_col(sel_idx, num_items_before, term_w))
        band = gold_fg() + BOLD + "★" * self._CARD_W + RESET
        pulse_text(
            card_row,
            col,
            band,
            frames=4,
            frame_delay=0.04,
            reader=self.reader,
            colors=(gold_fg() + BOLD, white_fg() + BOLD),
        )

        # Money tick-down via a single-line redraw helper.
        def _paint_money(val: int) -> None:
            line = ansi_center(white_fg() + "Money: " + green_fg() + f"${val}" + RESET, term_w)
            sys.stdout.write(move(money_row, 1) + line)
            sys.stdout.flush()

        tick_bar(
            money_before,
            money_after,
            render_fn=_paint_money,
            frames=8,
            frame_delay=0.03,
            reader=self.reader,
        )

    def _animate_reroll(self, num_items: int) -> None:
        """Briefly dim the existing card row before the new inventory paints.

        The next `_render()` call handles drawing the fresh cards; this
        helper just supplies the "out" half of the transition. No timing
        bound other than its own ~150ms.
        """
        from belote.ui.anim import animations_enabled, pulse_text
        from belote.ui.render import get_term_size

        if not animations_enabled():
            return

        term_w, term_h = get_term_size()
        card_row = self._rows(term_h)["cards"]

        # Wipe the card row with a centered "rerolling..." marker that
        # pulses gold→white→gold. Cheap fade-out cue without per-card art.
        msg = "↻ rerolling..."
        text = ansi_center(gold_fg() + BOLD + msg + RESET, term_w)
        pulse_text(
            card_row + 4,  # mid-height of the 9-row planet card
            1,
            text,
            frames=4,
            frame_delay=0.03,
            reader=self.reader,
            colors=(gold_fg() + BOLD, white_fg() + BOLD),
        )
