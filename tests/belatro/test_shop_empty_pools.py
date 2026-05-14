"""Shop generates an empty inventory cleanly when registry pools are empty (B2).

`Shop.generate_inventory` guards each pool sampling with `if pool_ids:`. The
degenerate case (no items available for the current Profile / unlock state)
should yield an empty inventory and never raise — even though it's nearly
impossible in practice.
"""

from __future__ import annotations

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.run.shop import Shop


def _empty_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every pool on the live registry with empty dicts and bump the
    generation so the cached `get_available_*` views miss.

    Callers MUST construct the run/shop FIRST, then call this — `BelAtroRun.
    __post_init__` re-registers items if it sees an empty `registry.planets`.
    """
    monkeypatch.setattr(registry, "jokers", {})
    monkeypatch.setattr(registry, "tarots", {})
    monkeypatch.setattr(registry, "planets", {})
    monkeypatch.setattr(registry, "vouchers", {})
    registry._bump()


def test_generate_inventory_empty_pools_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_all_items()
    run = BelAtroRun(seed=42)
    shop = Shop(run)
    _empty_pools(monkeypatch)
    shop.generate_inventory()
    assert shop.inventory == []


def test_buy_index_oob_on_empty_inventory_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling buy_item on an empty shop should fail gracefully, not crash."""
    register_all_items()
    run = BelAtroRun(seed=42)
    run.economy.money = 100
    shop = Shop(run)
    _empty_pools(monkeypatch)
    shop.generate_inventory()
    assert shop.buy_item(0) is False
    assert run.economy.money == 100  # no money consumed


def test_reroll_on_empty_pools_stays_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rerolling can't conjure items from an empty registry, but shouldn't
    leak state or crash."""
    register_all_items()
    run = BelAtroRun(seed=42)
    run.economy.money = 100
    shop = Shop(run)
    _empty_pools(monkeypatch)
    shop.generate_inventory()
    cost_before = shop.reroll_cost
    shop.reroll()
    assert shop.inventory == []
    # Reroll still charged the player (the pool was empty regardless of
    # whether they could see new items).
    assert run.economy.money < 100
    assert shop.reroll_cost == cost_before + 1


def test_partial_empty_pools_produces_what_it_can(monkeypatch: pytest.MonkeyPatch) -> None:
    """If only some pools are empty (e.g. all vouchers owned), the shop should
    still surface items from the non-empty pools."""
    register_all_items()
    run = BelAtroRun(seed=42)
    shop = Shop(run)
    # Empty vouchers only — jokers / tarots / planets remain populated.
    monkeypatch.setattr(registry, "vouchers", {})
    registry._bump()
    shop.generate_inventory()
    # Should produce 0-3 items (up to 2 jokers + 1 tarot/planet, no voucher).
    assert 0 <= len(shop.inventory) <= 3
    from belote.belatro.items.base import Voucher

    assert not any(isinstance(it, Voucher) for it in shop.inventory)
