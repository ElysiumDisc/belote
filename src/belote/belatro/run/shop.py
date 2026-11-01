from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from ..progression.save import Profile


class Shop:
    """Manages randomized item generation and purchases between rounds."""

    def __init__(
        self, run: BelAtroRun, profile: Profile | None = None, pool: Profile | None = None
    ) -> None:
        self.run = run
        self.profile = profile  # discoveries are recorded here
        # Whose unlocks decide what can appear (defaults to `profile`). The
        # Daily Challenge passes a fresh Profile so every player's shop rolls
        # from the same pool and seeded runs stay in step.
        self.pool = pool
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
        ("neg", 0.02),
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

        prof = self.pool or self.profile or Profile()
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
        # Never offer a joker the run already owns: duplicates share their
        # `f"{id}_..."` joker_state keys and corrupt each other (double-pay,
        # one copy never firing). If every unlocked joker is owned the joker
        # row is simply left empty rather than offering a duplicate.
        partner = getattr(self.run, "partner", None)
        owned_ids = {
            getattr(j, "id", None) for j in [*self.run.jokers, *getattr(partner, "jokers", [])]
        }
        joker_ids = [j_id for j_id in available_jokers if j_id not in owned_ids]
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

        # 4.11.0 Le Téléphone: sometimes an extra Partner Joker that equips on
        # the partner's own slots. Drawn last, and only with the voucher, so
        # every other shop rolls exactly as before.
        if getattr(self.run, "partner_joker_offers", False):
            self._offer_partner_joker(rng, available_jokers, owned_ids)

    # Le Téléphone: chance per shop of a partner-slot offer.
    PARTNER_OFFER_CHANCE = 0.5

    def _offer_partner_joker(self, rng: Any, available: dict[str, Any], owned: set[Any]) -> None:
        if rng.random() >= self.PARTNER_OFFER_CHANCE:
            return
        offered = {getattr(i, "id", None) for i in self.inventory}
        pool = [
            j_id
            for j_id, cls in available.items()
            if cls.is_partner_joker and j_id not in owned and j_id not in offered
        ]
        if not pool:
            return
        j_id = rng.choice(pool)
        item: Any = available[j_id]()
        item.for_partner = True
        self.inventory.append(item)
        if self.profile:
            self.profile.discover(j_id)

    def reroll(self) -> bool:
        """Pay to refresh the shop inventory."""
        cost = self.reroll_cost
        if self.run.economy.spend_money(cost):
            self.generate_inventory()
            self.reroll_cost += 1
            recorder = getattr(self.run, "recorder", None)
            if recorder is not None:
                recorder.note_reroll(cost)
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
            recorder = getattr(self.run, "recorder", None)
            if recorder is not None:
                recorder.note_buy(item, item.cost)
            return True
        self.last_buy_failure = "no_money"
        return False

    @staticmethod
    def sell_value(joker: object) -> int:
        """Money a joker sells for: half its (edition-adjusted) cost.

        Same formula La Tempérance uses for "total sell value".
        """
        return int(getattr(joker, "cost", 0)) // 2

    def can_sell(self, index: int) -> bool:
        """Corrupted jokers can't be sold — their curse was the price of the
        power, and selling would refund it while keeping the run flags."""
        if not (0 <= index < len(self.run.jokers)):
            return False
        return not getattr(self.run.jokers[index], "is_corrupted", False)

    def sell_joker(self, index: int) -> int:
        """Sell the owned joker at `index`. Returns the money gained (0 = refused).

        A Negative-edition joker had grown `joker_slots` by one when bought,
        so selling it gives that slot back.
        """
        if not self.can_sell(index):
            return 0
        from ..items.base import Edition

        joker = self.run.jokers.pop(index)
        if getattr(joker, "edition", Edition.NONE) == Edition.NEGATIVE:
            self.run.joker_slots = max(len(self.run.jokers), self.run.joker_slots - 1)
        value = self.sell_value(joker)
        if value > 0:
            self.run.economy.add_money(value)
        recorder = getattr(self.run, "recorder", None)
        if recorder is not None:
            recorder.note_sell(joker, value)
        return value

    def _can_accept(self, item: object) -> bool:
        """True iff `item` can be placed somewhere on the run right now.

        Negative-edition jokers always fit (they grow `joker_slots` instead of
        consuming one). Vouchers don't compete for a slot. Tarot/Planet land
        in `run.consumables`.
        """
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, Joker):
            if item.for_partner:
                partner = self.run.partner
                return len(partner.jokers) < partner.joker_slots
            if item.edition == Edition.NEGATIVE:
                return True
            return len(self.run.jokers) < self.run.joker_slots
        if isinstance(item, Voucher):
            return True
        return len(self.run.consumables) < self.run.consumable_slots

    def _apply_item(self, item: object) -> None:
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, Joker) and item.for_partner:
            # Le Téléphone offer: the partner's own slots (capacity checked
            # in _can_accept); on_purchase fires through equip_joker.
            self.run.partner.equip_joker(item, self.run)
        elif isinstance(item, Joker):
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
            # 3.9.3: idempotency guard relocated to Voucher.apply() itself,
            # so any caller (shop, replay, future save/load) gets the same
            # protection. The base wraps the subclass's `_apply_once` and
            # consults `run._applied_voucher_ids` automatically. Calling
            # apply() unconditionally is now safe.
            item.apply(self.run)
        elif len(self.run.consumables) < self.run.consumable_slots:
            self.run.consumables.append(item)
