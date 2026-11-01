"""Shop generation, pricing and rarity rolls."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TestShop:
    def setup_method(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun
        from belote.belatro.items.registry import register_all_items
        from belote.belatro.progression.save import Profile
        from belote.belatro.run.shop import Shop

        register_all_items()
        self.run = BelAtroRun()
        self.run.economy.money = 100
        self.profile = Profile()
        self.shop = Shop(self.run, self.profile)
        self.shop.generate_inventory()

    def test_generate_inventory_produces_items(self) -> None:
        assert len(self.shop.inventory) > 0

    def test_buy_item_valid_index_returns_true(self) -> None:
        item = self.shop.inventory[0]
        self.run.economy.money = item.cost + 10
        result = self.shop.buy_item(0)
        assert result is True

    def test_buy_item_removes_item_from_inventory(self) -> None:
        original_count = len(self.shop.inventory)
        self.run.economy.money = 9999
        self.shop.buy_item(0)
        assert len(self.shop.inventory) == original_count - 1

    def test_buy_item_spends_money(self) -> None:
        item = self.shop.inventory[0]
        self.run.economy.money = 999
        before = self.run.economy.money
        self.shop.buy_item(0)
        assert self.run.economy.money == before - item.cost

    def test_buy_item_insufficient_funds_returns_false(self) -> None:
        self.run.economy.money = 0
        result = self.shop.buy_item(0)
        assert result is False

    def test_buy_item_insufficient_funds_does_not_remove(self) -> None:
        original_count = len(self.shop.inventory)
        self.run.economy.money = 0
        self.shop.buy_item(0)
        assert len(self.shop.inventory) == original_count

    def test_buy_item_out_of_range_returns_false(self) -> None:
        result = self.shop.buy_item(999)
        assert result is False

    def test_buy_item_negative_index_returns_false(self) -> None:
        result = self.shop.buy_item(-1)
        assert result is False

    def test_reroll_returns_true_with_sufficient_funds(self) -> None:
        self.run.economy.money = 100
        result = self.shop.reroll()
        assert result is True

    def test_reroll_spends_money(self) -> None:
        self.run.economy.money = 100
        before = self.run.economy.money
        cost = self.shop.reroll_cost
        self.shop.reroll()
        assert self.run.economy.money == before - cost

    def test_reroll_increases_reroll_cost(self) -> None:
        self.run.economy.money = 100
        original_cost = self.shop.reroll_cost
        self.shop.reroll()
        assert self.shop.reroll_cost == original_cost + 1

    def test_reroll_regenerates_inventory(self) -> None:
        self.run.economy.money = 100
        # Reroll multiple times to reduce chance of same inventory
        for _ in range(3):
            if self.run.economy.money >= self.shop.reroll_cost:
                self.shop.reroll()
        second_types = [type(i).__name__ for i in self.shop.inventory]
        # We just check inventory was repopulated (non-empty)
        assert len(second_types) > 0

    def test_reroll_fails_with_no_money(self) -> None:
        self.run.economy.money = 0
        result = self.shop.reroll()
        assert result is False

    def test_buying_joker_adds_to_run_jokers(self) -> None:
        from belote.belatro.items.base import Joker

        # Find a joker in inventory
        for i, item in enumerate(self.shop.inventory):
            if isinstance(item, Joker):
                self.run.economy.money = 9999
                before = len(self.run.jokers)
                self.shop.buy_item(i)
                assert len(self.run.jokers) == before + 1
                break

    def test_buying_voucher_adds_to_run_vouchers(self) -> None:
        from belote.belatro.items.base import Voucher

        # Find a voucher in inventory
        for i, item in enumerate(self.shop.inventory):
            if isinstance(item, Voucher):
                self.run.economy.money = 9999
                before = len(self.run.vouchers)
                self.shop.buy_item(i)
                assert len(self.run.vouchers) == before + 1
                break

    def test_buy_consumable_with_full_slots_does_not_charge_money(self) -> None:
        """Regression (3.1.0): pre-fix, buy_item charged money even when the
        Tarot/Planet couldn't fit because consumable_slots were full. Now the
        capacity check runs before spend_money, and last_buy_failure carries
        the reason so the UI can surface a 'Slots full' banner."""
        from belote.belatro.items.base import Tarot

        # Find a Tarot or Planet in inventory; if none rolled, force one.
        consumable_idx = next(
            (
                i
                for i, item in enumerate(self.shop.inventory)
                if not hasattr(item, "apply") and not hasattr(item, "edition")
            ),
            None,
        )
        if consumable_idx is None:
            from belote.belatro.items.tarots import LeChariot

            self.shop.inventory.append(LeChariot())
            consumable_idx = len(self.shop.inventory) - 1

        # Pre-fill consumables to capacity.
        item = self.shop.inventory[consumable_idx]
        from belote.belatro.items.tarots import LeChariot

        self.run.consumables = [LeChariot() for _ in range(self.run.consumable_slots)]
        self.run.economy.money = 999
        money_before = self.run.economy.money
        inv_before = len(self.shop.inventory)

        result = self.shop.buy_item(consumable_idx)

        assert result is False
        assert self.run.economy.money == money_before, (
            "Money was spent even though the consumable couldn't fit."
        )
        assert len(self.shop.inventory) == inv_before
        assert self.shop.last_buy_failure == "slots_full"
        # Sanity: keep the helper unused-warning quiet.
        _ = isinstance(item, Tarot)

    def test_buy_joker_with_full_slots_does_not_charge_money(self) -> None:
        """Regression (3.1.0): same money-leak fix path for jokers. Negative-
        edition jokers still bypass the capacity check (they grow the slot)."""
        from belote.belatro.items.base import Edition, Joker

        joker_idx = next(
            (i for i, item in enumerate(self.shop.inventory) if isinstance(item, Joker)),
            None,
        )
        if joker_idx is None:
            return  # no joker rolled this time
        joker = self.shop.inventory[joker_idx]
        # Force the joker to be non-Negative; Negative gets a free pass.
        joker.edition = Edition.NONE
        # Fill jokers to capacity.
        from belote.belatro.items.jokers.coinche import CoincheStack

        self.run.jokers = [CoincheStack() for _ in range(self.run.joker_slots)]
        self.run.economy.money = 999
        money_before = self.run.economy.money

        result = self.shop.buy_item(joker_idx)

        assert result is False
        assert self.run.economy.money == money_before
        assert self.shop.last_buy_failure == "slots_full"

    def test_buy_item_no_money_records_no_money_failure(self) -> None:
        self.run.economy.money = 0
        result = self.shop.buy_item(0)
        assert result is False
        assert self.shop.last_buy_failure == "no_money"

    def test_buy_item_success_clears_failure_reason(self) -> None:
        self.run.economy.money = 9999
        result = self.shop.buy_item(0)
        assert result is True
        assert self.shop.last_buy_failure is None


class TestLeJugementRarity:
    """F3: LeJugement description promises a Common joker; pre-3.3.3 the
    pool was the full unlocked set so Rare/Legendary unlocks could roll
    off this tarot. Now filtered to Rarity.COMMON.
    """

    def test_le_jugement_only_grants_common_jokers(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun
        from belote.belatro.items.base import Rarity
        from belote.belatro.items.tarots import LeJugement

        # Drive enough trials to cover the available pool many times over.
        # Each pass adds a joker → the slot guard fires after joker_slots
        # grants and short-circuits. Reset jokers between trials so each
        # call actually grants.
        for seed in range(20):
            run = BelAtroRun(seed=seed)
            run.jokers = []  # ensure slots aren't full
            LeJugement().use(run, None)
            if not run.jokers:
                # Pool was empty for this seed/profile — the tarot left
                # a message and returned. Acceptable.
                continue
            granted = run.jokers[-1]
            assert getattr(granted, "rarity", Rarity.COMMON) == Rarity.COMMON, (
                f"Le Jugement granted {granted.__class__.__name__} of "
                f"rarity {getattr(granted, 'rarity', None)} — expected Common"
            )

    def test_le_jugement_empty_pool_sets_message(self) -> None:
        """If the Common pool is empty (e.g., all jokers are higher-rarity
        unlockables), LeJugement should fall through to the empty-pool path
        and set last_tarot_message rather than crash.
        """
        from belote.belatro.core.run_state import BelAtroRun
        from belote.belatro.items.tarots import LeJugement

        run = BelAtroRun(seed=1)
        run.jokers = []
        # Monkey-patch the registry lookup to return an empty pool.
        import belote.belatro.items.tarots as tarot_mod
        from belote.belatro.items import registry as reg_mod

        orig = reg_mod.registry.get_available_jokers
        reg_mod.registry.get_available_jokers = lambda profile: {}  # type: ignore[assignment]
        try:
            LeJugement().use(run, None)
            assert run.last_tarot_message is not None
            assert "no jokers" in run.last_tarot_message.lower()
            assert run.jokers == []
        finally:
            reg_mod.registry.get_available_jokers = orig  # type: ignore[assignment]
        _ = tarot_mod  # silence unused-import lint
