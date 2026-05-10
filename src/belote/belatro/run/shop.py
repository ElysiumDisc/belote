from __future__ import annotations

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
        # Reason the most recent buy_item() returned False, or None on success.
        # The shop UI consults this to surface "Slots full" vs "Not enough $".
        self.last_buy_failure: str | None = None

    # 3.0.0: edition roll table at shop generation. ~80% NONE, then a tail
    # of Foil/Holo/Polychrome/Negative. Calibrated so a typical 8-ante run
    # surfaces 1-2 edited jokers. Negative is rare because it grants a
    # permanent extra slot.
    _EDITION_WEIGHTS: tuple[tuple[str, float], ...] = (
        ("none", 0.80),
        ("foil", 0.08),
        ("holo", 0.06),
        ("poly", 0.04),
        ("neg",  0.02),
    )

    def _roll_edition(self, rng: Any) -> str:
        roll = rng.random()
        cum = 0.0
        for name, w in self._EDITION_WEIGHTS:
            cum += w
            if roll < cum:
                return name
        return "none"

    def generate_inventory(self) -> None:
        """Populate the shop with a mix of items."""
        from ..items.base import Edition
        from ..items.registry import registry
        from ..progression.save import Profile

        prof = self.profile or Profile()
        self.inventory = []
        # Use the run's seeded RNG so shop generation is deterministic when
        # run.seed is set. Pre-3.2 the shop used the module-level `random`,
        # which made shop contents non-deterministic even with a seeded run
        # — breaking ghost-run replays.
        rng = self.run._get_rng()

        # 2 distinct Jokers (filtered by unlock). sample so the same joker
        # can't show up twice in one shop. If the unlocked pool is smaller
        # than 2, take whatever's available without padding.
        available_jokers = registry.get_available_jokers(prof)
        joker_ids = list(available_jokers.keys())
        if joker_ids:
            picks = rng.sample(joker_ids, k=min(2, len(joker_ids)))
            for j_id in picks:
                j_item: Any = available_jokers[j_id]()
                # Roll edition. Foil/Holo/Polychrome/Negative each adjust the
                # cost slightly so the tooltip price reflects the bonus.
                edition_name = self._roll_edition(rng)
                j_item.edition = Edition(edition_name)
                if edition_name != "none":
                    j_item.cost = int(j_item.cost * 1.5)
                self.inventory.append(j_item)
                if self.profile:
                    self.profile.discover(j_id)

        # 1 Tarot or Planet (Le Grimoire guarantees a tarot)
        force_tarot = getattr(self.run, "guarantee_tarot_in_shop", False)
        if force_tarot or rng.random() < 0.5:
            tarot_ids = list(registry.tarots.keys())
            if tarot_ids:
                t_id = rng.choice(tarot_ids)
                tarot_cls = registry.get_tarot(t_id)
                if tarot_cls:
                    t_item: Any = tarot_cls()
                    self.inventory.append(t_item)
                    if self.profile:
                        self.profile.discover(t_id)
        else:
            planet_ids = list(registry.planets.keys())
            if planet_ids:
                p_id = rng.choice(planet_ids)
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
            v_id = rng.choice(voucher_ids)
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
        """Attempt to buy an item from the inventory.

        Slot capacity is checked BEFORE charging the player. Pre-3.1.0 the
        money was spent unconditionally and the item was silently dropped if
        no slot fit — a money-leak bug under full joker/consumable slots.
        """
        if not (0 <= index < len(self.inventory)):
            return False
        item = self.inventory[index]
        if not self._can_accept(item):
            self.last_buy_failure = "slots_full"
            return False
        if self.run.economy.spend_money(item.cost):
            self._apply_item(item)
            self.inventory.pop(index)
            self.last_buy_failure = None
            return True
        self.last_buy_failure = "no_money"
        return False

    def _can_accept(self, item: object) -> bool:
        """True iff `item` can be placed somewhere on the run right now.

        Negative-edition jokers always fit (they grow `joker_slots` instead of
        consuming one). Vouchers don't compete for a slot. Tarot/Planet land
        in `run.consumables`.
        """
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, Joker):
            if item.edition == Edition.NEGATIVE:
                return True
            return len(self.run.jokers) < self.run.joker_slots
        if isinstance(item, Voucher):
            return True
        return len(self.run.consumables) < self.run.consumable_slots

    def _apply_item(self, item: object) -> None:
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, Joker):
            # 3.0.0: Negative-edition jokers don't consume a slot — they grow
            # the run's slot count instead. Other editions follow the normal
            # capacity check.
            if item.edition == Edition.NEGATIVE:
                self.run.joker_slots += 1
                self.run.jokers.append(item)
                item.on_purchase(self.run)
            elif len(self.run.jokers) < self.run.joker_slots:
                self.run.jokers.append(item)
                item.on_purchase(self.run)
        elif isinstance(item, Voucher):
            self.run.vouchers.append(item)
            item.apply(self.run)
        elif len(self.run.consumables) < self.run.consumable_slots:
            self.run.consumables.append(item)
