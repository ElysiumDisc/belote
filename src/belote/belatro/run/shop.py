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
        # 5.0.0: set when the player chose to skip the next blind (the run
        # loop then skips it and grants `skip_medal`).
        self.skip_next = False
        self.skip_medal: str | None = None
        # Reason the most recent buy_item() returned False, or None on success.
        # The shop UI consults this to surface "Slots full" vs "Not enough $".
        self.last_buy_failure: str | None = None
        # 5.0.0: per-roll knobs. Médailles (`run/medals.py`) set them for the
        # shop's first roll only; `generate_inventory` resets them after.
        self.copy_chance = self.COPY_CHANCE
        self.extra_jokers = 0
        self.guaranteed_edition = False
        self.free_jokers = False
        self.free_card_mod = False
        self.free_tarot = False

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

    # 5.0.0: chance that a joker offer is a copy of one the player owns.
    COPY_CHANCE = 0.12

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
        from ..items.registry import registry
        from ..progression.save import Profile

        prof = self.pool or self.profile or Profile()
        self.inventory = []
        # Use the run's seeded RNG so shop generation is deterministic when
        # run.seed is set. Pre-3.2 the shop used the module-level `random`,
        # which made shop contents non-deterministic even with a seeded run
        # — breaking ghost-run replays.
        rng = self.run._get_rng()

        available_jokers = registry.get_available_jokers(prof)
        owned_ids = self._offer_jokers(rng, available_jokers)
        self._offer_consumable(rng)
        self._offer_voucher(rng, prof)

        # 5.0.0 L'Atelier: one per-card enhancement / seal every roll, and Le
        # Cartomancien's free tarot (medal).
        self._offer_card_mod(rng)
        if self.free_tarot:
            self._offer_free_tarot(rng)

        # 4.11.0 Le Téléphone: sometimes an extra Partner Joker that equips on
        # the partner's own slots. Drawn last, and only with the voucher, so
        # every other shop rolls exactly as before.
        if getattr(self.run, "partner_joker_offers", False):
            self._offer_partner_joker(rng, available_jokers, owned_ids)
        self._reset_roll_knobs()

    def _offer_jokers(self, rng: Any, available_jokers: dict[str, Any]) -> set[Any]:
        """2 Jokers (filtered by unlock); returns the owned ids.

        The fresh offers are sampled from the jokers the run doesn't own, so
        the same joker can't show up twice by accident. 5.0.0: copies are safe
        now (`Joker.state_key`), so each offer may instead be a copy of a joker
        in the player's slots (`copy_chance`) — the road to Le Serment's
        three-copy oath.
        """
        partner = getattr(self.run, "partner", None)
        owned_ids = {
            getattr(j, "id", None) for j in [*self.run.jokers, *getattr(partner, "jokers", [])]
        }
        joker_ids = [j_id for j_id in available_jokers if j_id not in owned_ids]
        count = 2 + self.extra_jokers
        offers = rng.sample(joker_ids, k=min(count, len(joker_ids))) if joker_ids else []
        copyable = sorted({j.id for j in self.run.jokers if j.id in available_jokers})
        for i in range(count):
            if copyable and rng.random() < self.copy_chance:
                copy_id = rng.choice(copyable)
                if i < len(offers):
                    offers[i] = copy_id
                else:
                    offers.append(copy_id)
        for i, j_id in enumerate(offers):
            self.inventory.append(self._joker_offer(rng, available_jokers[j_id], first=i == 0))
            if self.profile:
                self.profile.discover(j_id)
        return owned_ids

    def _joker_offer(self, rng: Any, cls: Any, *, first: bool) -> Any:
        """One joker offer with its rolled edition. Foil/Holo/Polychrome/
        Negative raise the price so the tooltip reflects the bonus."""
        from ..items.base import Edition

        item: Any = cls()
        edition_name = self._roll_edition(rng)
        if first and self.guaranteed_edition and edition_name in ("none", "neg"):
            edition_name = rng.choice(("foil", "holo", "poly"))  # L'Antiquaire
        item.edition = Edition(edition_name)
        if edition_name != "none":
            item.cost = int(item.cost * 1.5)
        if self.free_jokers:
            item.cost = 0  # Le Mécène
        return item

    def _offer_consumable(self, rng: Any) -> None:
        """1 Tarot or Planet (Le Grimoire guarantees a tarot)."""
        from ..items.registry import registry

        force_tarot = getattr(self.run, "guarantee_tarot_in_shop", False)
        if force_tarot or rng.random() < 0.5:
            pool: dict[str, Any] = registry.tarots
        else:
            pool = registry.planets
        item_ids = list(pool.keys())
        if not item_ids:
            return
        item_id = rng.choice(item_ids)
        self.inventory.append(pool[item_id]())
        if self.profile:
            self.profile.discover(item_id)

    def _offer_voucher(self, rng: Any, prof: Any) -> None:
        """1 Voucher (if available, unlocked and not already owned)."""
        from ..items.registry import registry

        available_vouchers = registry.get_available_vouchers(prof)
        voucher_ids = [
            v_id
            for v_id, v_cls in available_vouchers.items()
            if not any(isinstance(v, v_cls) for v in self.run.vouchers)
        ]
        if voucher_ids:
            v_id = rng.choice(voucher_ids)
            self.inventory.append(available_vouchers[v_id]())
            if self.profile:
                self.profile.discover(v_id)

    def _offer_card_mod(self, rng: Any) -> None:
        from belote.deck import make_deck

        from ..core.card_mods import MOD_COST, CardModOffer, card_key

        mod_id = rng.choice(sorted(MOD_COST))
        mods = getattr(self.run, "card_mods", {})

        def carries(card: Any) -> bool:
            entry = mods.get(card_key(card))
            return entry is not None and mod_id in (entry.enhancement, entry.seal)

        cards = [c for c in make_deck() if not carries(c)]
        if not cards:
            return
        card = rng.choice(cards)
        cost = 0 if self.free_card_mod else MOD_COST[mod_id]
        self.inventory.append(CardModOffer(card=card, mod_id=mod_id, cost=cost))

    def _offer_free_tarot(self, rng: Any) -> None:
        from ..items.registry import registry

        tarot_ids = sorted(registry.tarots)
        if not tarot_ids:
            return
        t_id = rng.choice(tarot_ids)
        item: Any = registry.tarots[t_id]()
        item.cost = 0
        self.inventory.append(item)
        if self.profile:
            self.profile.discover(t_id)

    def _reset_roll_knobs(self) -> None:
        """Médaille effects last one roll: a reroll is an ordinary shop."""
        self.copy_chance = self.COPY_CHANCE
        self.extra_jokers = 0
        self.guaranteed_edition = False
        self.free_jokers = False
        self.free_card_mod = False
        self.free_tarot = False

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

    # ── 5.0.0: Le Serment, Médailles, skipping the next blind ──────────

    def available_fusions(self) -> list[Any]:
        from .fusion import available_fusions

        return available_fusions(self.run)

    def fuse(self, fusion: Any) -> Any:
        from .fusion import fuse

        return fuse(self.run, fusion)

    def spend_medals(self) -> list[Any]:
        """Apply the run's waiting medals to this shop's first roll."""
        from .medals import apply_medals

        return apply_medals(self.run, self)

    def skip_offer(self) -> Any:
        from .medals import skip_offer

        return skip_offer(self.run)

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
        from ..core.card_mods import CardModOffer
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, CardModOffer):
            return True
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
        from ..core.card_mods import CardModOffer, apply_mod
        from ..items.base import Edition, Joker, Voucher

        if isinstance(item, CardModOffer):
            apply_mod(self.run.card_mods, item.card, item.mod_id)
            if self.profile:
                self.profile.discover(item.id)
        elif isinstance(item, Joker) and item.for_partner:
            # Le Téléphone offer: the partner's own slots (capacity checked
            # in _can_accept); on_purchase fires through equip_joker.
            self.run.partner.equip_joker(item, self.run)
        elif isinstance(item, Joker):
            # 3.0.0: Negative-edition jokers don't consume a slot — they grow
            # the run's slot count instead. Other editions follow the normal
            # capacity check.
            if item.edition == Edition.NEGATIVE:
                self.run.joker_slots += 1
                self.run.add_joker(item)
            elif len(self.run.jokers) < self.run.joker_slots:
                self.run.add_joker(item)
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
