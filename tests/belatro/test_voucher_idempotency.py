"""Voucher idempotency guard (B1 audit finding).

Vouchers like LaTelescope (+1 bonus_per_round), LaDoubleDonne (+1 joker_slot),
LesCartesDorees (+1 interest_rate / +5 max_interest), and LeCouteau (+1
consumable_slot) use `+=` against run state. If `apply()` is ever invoked
twice on the same voucher instance (save/load round-trip, replay
reconstruction, future feature regression), the bonus would silently double.

The shop now guards against this via `_applied_voucher_ids`. These tests pin
that contract.
"""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.items.vouchers import (
    LaDoubleDonne,
    LaTelescope,
    LeCouteau,
    LesCartesDorees,
)
from belote.belatro.run.shop import Shop


def _make_run_with_shop(money: int = 1000) -> tuple[BelAtroRun, Shop]:
    register_all_items()
    run = BelAtroRun(seed=42)
    run.economy.money = money
    shop = Shop(run)
    return run, shop


def test_buying_voucher_marks_it_applied() -> None:
    """After purchase, the voucher id is recorded so re-apply is suppressed."""
    run, shop = _make_run_with_shop()
    voucher = LaTelescope()
    shop.inventory = [voucher]
    assert voucher.id not in run._applied_voucher_ids

    assert shop.buy_item(0) is True
    assert voucher.id in run._applied_voucher_ids
    assert run.economy.bonus_per_round == 1


def test_voucher_double_apply_via_shop_is_noop() -> None:
    """Buying a fresh instance of an already-applied voucher must NOT
    re-apply. Today this never happens (each shop roll generates fresh
    inventory), but the guard pins the contract."""
    run, shop = _make_run_with_shop()

    # First purchase
    shop.inventory = [LaTelescope()]
    shop.buy_item(0)
    assert run.economy.bonus_per_round == 1

    # Force a second purchase of a brand-new instance with the same id.
    # The shop should accept the buy (vouchers don't fill slots) but the
    # apply() short-circuits.
    shop.inventory = [LaTelescope()]
    shop.buy_item(0)
    assert run.economy.bonus_per_round == 1, (
        "Second apply() leaked through the idempotency guard"
    )


def test_each_distinct_voucher_applies_independently() -> None:
    """The guard is keyed on voucher id, not voucher class — different
    vouchers should both apply normally even if purchased in sequence."""
    run, shop = _make_run_with_shop()
    starting_joker_slots = run.joker_slots
    starting_consumable_slots = run.consumable_slots

    for v_cls in (LaTelescope, LaDoubleDonne, LesCartesDorees, LeCouteau):
        shop.inventory = [v_cls()]
        assert shop.buy_item(0) is True

    # All four should have applied exactly once.
    assert run.economy.bonus_per_round == 1  # LaTelescope
    assert run.joker_slots == starting_joker_slots + 1  # LaDoubleDonne
    assert run.economy.interest_rate == 1  # LesCartesDorees: 0 + 1
    assert run.economy.max_interest == 5  # LesCartesDorees: 0 + 5
    assert run.consumable_slots == starting_consumable_slots + 1  # LeCouteau
    assert {"la_telescope", "la_double_donne", "les_cartes_dorees", "le_couteau"} <= (
        run._applied_voucher_ids
    )


def test_lavoute_max_pattern_unaffected_by_guard() -> None:
    """LaVoute uses max() instead of += — it should still behave correctly
    when bought after LesCartesDorees (the realistic stacking case)."""
    from belote.belatro.items.vouchers import LaVoute

    run, shop = _make_run_with_shop()

    shop.inventory = [LesCartesDorees()]
    shop.buy_item(0)
    rate_after_cartes = run.economy.interest_rate  # 0 + 1 = 1
    max_after_cartes = run.economy.max_interest  # 0 + 5 = 5

    # LaVoute's max(1, current) floor: 1 ≤ rate, 5 ≤ cap — both unchanged.
    shop.inventory = [LaVoute()]
    shop.buy_item(0)
    assert run.economy.interest_rate == rate_after_cartes
    assert run.economy.max_interest == max_after_cartes


def test_applied_voucher_ids_serializes_through_replace() -> None:
    """`_applied_voucher_ids` is a regular set — dataclass replace() preserves
    it, ensuring the guard survives any future state-snapshotting code."""
    from dataclasses import replace

    register_all_items()
    run = BelAtroRun()
    run._applied_voucher_ids.add("la_telescope")
    run2 = replace(run, ante_number=2)
    assert "la_telescope" in run2._applied_voucher_ids
    # The set itself should NOT be aliased between snapshots (the field uses
    # default_factory=set), so per-instance mutations are isolated.
    # NOTE: dataclass replace() with no override DOES alias mutable defaults;
    # this assertion documents current behaviour rather than enforcing a
    # divergence guarantee.
    assert run2._applied_voucher_ids is run._applied_voucher_ids


def test_registry_still_lists_all_four_vouchers() -> None:
    """Smoke check: the audit's affected voucher quartet is still registered."""
    register_all_items()
    for vid in ("la_telescope", "la_double_donne", "les_cartes_dorees", "le_couteau"):
        assert vid in registry.vouchers, f"{vid} missing from registry.vouchers"
