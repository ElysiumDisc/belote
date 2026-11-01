"""Scripted sessions through the BelAtro shop screen with a pinned
inventory: navigation, purchases (incl. slots-full and animations), reroll,
sell overlay (incl. corrupted jokers), consumables tray and the Tierce Forge."""

from __future__ import annotations

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.base import Edition
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.items.tarots import LeChariot
from belote.belatro.items.vouchers import TierceForge
from belote.belatro.run.shop import Shop
from belote.belatro.ui.shop import ShopScreen
from belote.ui import anim
from tests.harness import TUI, ScriptedReader, keys, raw_char


def _joker(jid: str | None = None, edition: Edition = Edition.NONE) -> object:
    cls = (
        registry.jokers[jid]
        if jid
        else next(c for c in registry.jokers.values() if not getattr(c, "is_corrupted", False))
    )
    j = cls()
    j.edition = edition
    return j


def _planet() -> object:
    return next(iter(registry.planets.values()))()


@pytest.fixture
def shop(monkeypatch: pytest.MonkeyPatch) -> Shop:
    """A shop whose inventory is pinned to [joker, planet, tarot]."""
    register_all_items()
    run = BelAtroRun(seed=5)
    run.economy.money = 100
    s = Shop(run)
    inv = [_joker(edition=Edition.FOIL), _planet(), LeChariot()]

    def gen() -> None:
        s.inventory = list(inv)

    monkeypatch.setattr(s, "generate_inventory", gen)
    return s


def _run(shop: Shop, reader: ScriptedReader) -> ShopScreen:
    screen = ShopScreen(shop, reader.as_reader())
    screen.run()
    return screen


def test_shop_renders_cards_money_hints_and_edition(tui: TUI, shop: Shop) -> None:
    _run(shop, tui.reader("esc"))
    text = tui.text
    assert "=== THE SHOP ===" in text
    assert "Money: $100" in text
    assert "[Foil: +50 chips per trigger]" in text  # selected joker's edition
    assert "Lv." in text  # planet card face
    assert f"[ Reroll ${shop.reroll_cost} ]" in text
    assert "C: Consumables (0)" in text
    assert "Forge" not in text


def test_shop_left_wraps_to_reroll_and_right_wraps_back(tui: TUI, shop: Shop) -> None:
    screen = _run(shop, tui.reader("left", "esc"))
    assert screen.selected == 3  # 3 items → reroll button
    screen = _run(shop, tui.reader("left", "right", "esc"))
    assert screen.selected == 0


def test_shop_buy_items_left_to_right(tui: TUI, shop: Shop) -> None:
    _run(shop, tui.reader("enter", "enter", "q"))
    assert len(shop.run.jokers) == 1
    assert len(shop.run.consumables) == 1  # the planet
    assert len(shop.inventory) == 1
    assert shop.run.economy.money < 100


def test_shop_buying_last_item_clamps_selection(tui: TUI, shop: Shop) -> None:
    screen = _run(shop, tui.reader("left", "left", "enter", "esc"))
    assert len(shop.inventory) == 2
    assert screen.selected == 1


def test_shop_slots_full_shows_sell_hint_banner(tui: TUI, shop: Shop) -> None:
    shop.run.joker_slots = 0
    # The banner swallows the dismiss key (space); then Esc leaves the shop.
    r = tui.reader("enter", "space", "esc")
    _run(shop, r)
    assert r.exhausted
    assert shop.run.jokers == []
    assert shop.run.economy.money == 100
    assert "Slots full — press S to sell a joker" in tui.text


def test_shop_no_money_purchase_is_refused_silently(tui: TUI, shop: Shop) -> None:
    shop.run.economy.money = 0
    _run(shop, tui.reader("enter", "esc"))
    assert shop.last_buy_failure == "no_money"
    assert len(shop.inventory) == 3


def test_shop_purchase_and_reroll_animations(tui: TUI, shop: Shop) -> None:
    anim.set_animations_enabled(True)
    cost = shop.reroll_cost
    # Buy the joker (animation polls read_timeout → None frames), then reroll.
    r = tui.reader("enter", "left", "enter", "esc", idle_timeouts=True)
    _run(shop, r)
    assert len(shop.run.jokers) == 1
    assert shop.reroll_cost == cost + 1
    assert "★★★★" in tui.text  # purchase pulse band
    assert "rerolling..." in tui.text
    assert r.timeouts  # animation frames polled the reader


def test_shop_reroll_without_money_keeps_inventory(tui: TUI, shop: Shop) -> None:
    shop.run.economy.money = 0
    cost = shop.reroll_cost
    _run(shop, tui.reader("left", "enter", "esc"))
    assert shop.reroll_cost == cost


# ── sell overlay ────────────────────────────────────────────────────────────


def test_shop_keyboard_s_opens_sell_overlay(tui: TUI, shop: Shop) -> None:
    shop.run.jokers.append(_joker())
    _run(shop, tui.reader(*keys("s"), "1", "space", "esc"))
    assert shop.run.jokers == []


def test_shop_sell_overlay_sells_and_refuses_corrupted(tui: TUI, shop: Shop) -> None:
    good = _joker()
    shop.run.jokers[:] = [registry.jokers["le_traitre"](), good]
    value = shop.sell_value(good)
    r = tui.reader(
        raw_char("s"), raw_char("x"), raw_char("9"), raw_char("1"), "space",  # corrupted
        raw_char("s"), raw_char("2"), "space",  # sell the good one
        "esc",
    )  # fmt: skip
    _run(shop, r)
    assert r.exhausted
    text = tui.text
    assert "SELL A JOKER" in text
    assert "(corrupted — can't sell)" in text
    assert "Le Traître is corrupted — can't sell" in text
    assert f"Sold {good.name} for ${value}" in text  # type: ignore[attr-defined]
    assert [j.id for j in shop.run.jokers] == ["le_traitre"]
    assert shop.run.economy.money == 100 + value


def test_shop_sell_overlay_cancel_and_empty(tui: TUI, shop: Shop) -> None:
    _run(shop, tui.reader(raw_char("s"), "space", "esc"))
    assert "No jokers to sell" in tui.text
    shop.run.jokers.append(_joker())
    _run(shop, tui.reader(raw_char("s"), "esc", "esc"))
    assert len(shop.run.jokers) == 1


# ── consumables tray ────────────────────────────────────────────────────────


def test_shop_consumables_tray_use_and_cancel(tui: TUI, shop: Shop) -> None:
    shop.run.consumables.append(LeChariot())
    _run(shop, tui.reader(raw_char("c"), "esc", "esc"))
    assert len(shop.run.consumables) == 1
    _run(shop, tui.reader(raw_char("C"), raw_char("1"), "space", "esc"))
    assert shop.run.consumables == []
    assert "Consumable activated." in tui.text


# ── Tierce Forge ────────────────────────────────────────────────────────────


@pytest.fixture
def forge_shop(shop: Shop) -> Shop:
    shop.run.vouchers.append(TierceForge())
    shop.run.tierce_charges = 3
    return shop


def test_forge_action_appears_and_levels_a_planet(tui: TUI, forge_shop: Shop) -> None:
    planet_cls = next(iter(registry.planets.values()))
    before = dict(forge_shop.run.contract_levels)
    # 3 items → reroll(3) → forge(4); LEFT from 0 wraps to the forge button.
    r = tui.reader("left", "enter", raw_char("x"), raw_char("1"), "space", "esc")
    _run(forge_shop, r)
    text = tui.text
    assert "[ Forge x3/3 ]" in text
    assert "Spend 3 Tierce charges to level up a Planet contract." in text
    assert "FORGE A PLANET" in text
    assert f"Forged: {planet_cls.name} levelled up!" in text
    assert forge_shop.run.tierce_charges == 0
    assert forge_shop.run.contract_levels != before


def test_forge_cancel_keeps_charges(tui: TUI, forge_shop: Shop) -> None:
    _run(forge_shop, tui.reader("left", "enter", "esc", "esc"))
    assert forge_shop.run.tierce_charges == 3


def test_forge_with_no_planets_is_a_no_op(
    tui: TUI, forge_shop: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "planets", {})
    _run(forge_shop, tui.reader("left", "enter", "esc"))
    assert forge_shop.run.tierce_charges == 3
    assert "FORGE A PLANET" not in tui.text


def test_forge_hidden_below_three_charges(tui: TUI, forge_shop: Shop) -> None:
    forge_shop.run.tierce_charges = 2
    screen = _run(forge_shop, tui.reader("left", "esc"))
    assert screen.selected == 3  # wraps to reroll, no forge slot
    assert "Forge" not in tui.text
