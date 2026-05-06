from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from ..progression.save import Profile


class Shop:
    """Manages randomized item generation and purchases between rounds."""

    def __init__(self, run: BelAtroRun, profile: Profile | None = None) -> None:
        self.run = run
        self.profile = profile
        self.inventory: list[Any] = []
        self.reroll_cost = 5

    def generate_inventory(self) -> None:
        """Populate the shop with a mix of items."""
        from ..items.registry import registry
        from ..progression.save import Profile

        prof = self.profile or Profile()
        self.inventory = []

        # 2 distinct Jokers (filtered by unlock). random.sample so the same
        # joker can't show up twice in one shop. If the unlocked pool is
        # smaller than 2, take whatever's available without padding.
        available_jokers = registry.get_available_jokers(prof)
        joker_ids = list(available_jokers.keys())
        if joker_ids:
            picks = random.sample(joker_ids, k=min(2, len(joker_ids)))
            for j_id in picks:
                j_item: Any = available_jokers[j_id]()
                self.inventory.append(j_item)
                if self.profile:
                    self.profile.discover(j_id)

        # 1 Tarot or Planet (Le Grimoire guarantees a tarot)
        force_tarot = getattr(self.run, "guarantee_tarot_in_shop", False)
        if force_tarot or random.random() < 0.5:
            tarot_ids = list(registry.tarots.keys())
            if tarot_ids:
                t_id = random.choice(tarot_ids)
                tarot_cls = registry.get_tarot(t_id)
                if tarot_cls:
                    t_item: Any = tarot_cls()
                    self.inventory.append(t_item)
                    if self.profile:
                        self.profile.discover(t_id)
        else:
            planet_ids = list(registry.planets.keys())
            if planet_ids:
                p_id = random.choice(planet_ids)
                planet_cls = registry.get_planet(p_id)
                if planet_cls:
                    p_item: Any = planet_cls()
                    self.inventory.append(p_item)
                    if self.profile:
                        self.profile.discover(p_id)

        # 1 Voucher (if available and unlocked)
        available_vouchers = registry.get_available_vouchers(prof)
        voucher_ids = [
            v_id
            for v_id, v_cls in available_vouchers.items()
            if not any(isinstance(v, v_cls) for v in self.run.vouchers)
        ]
        if voucher_ids:
            v_id = random.choice(voucher_ids)
            v_item: Any = available_vouchers[v_id]()
            self.inventory.append(v_item)
            if self.profile:
                self.profile.discover(v_id)

    def reroll(self) -> bool:
        """Pay to refresh the shop inventory."""
        if self.run.economy.spend_money(self.reroll_cost):
            self.generate_inventory()
            self.reroll_cost += 1
            return True
        return False

    def buy_item(self, index: int) -> bool:
        """Attempt to buy an item from the inventory."""
        if 0 <= index < len(self.inventory):
            item = self.inventory[index]
            if self.run.economy.spend_money(item.cost):
                self._apply_item(item)
                self.inventory.pop(index)
                return True
        return False

    def _apply_item(self, item: object) -> None:
        from ..items.base import Joker, Voucher

        if isinstance(item, Joker):
            if len(self.run.jokers) < self.run.joker_slots:
                self.run.jokers.append(item)
                item.on_purchase(self.run)
        elif isinstance(item, Voucher):
            self.run.vouchers.append(item)
            item.apply(self.run)
        elif len(self.run.consumables) < self.run.consumable_slots:
            self.run.consumables.append(item)
