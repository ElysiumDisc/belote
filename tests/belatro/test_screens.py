"""Pure line/frame builders behind the BelAtro full-screen overlays, plus
scripted sessions through the interactive shop."""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from belote.ansi import visible_len
from belote.input import Key, KeyEvent
from belote.ui.text import wrap_words

# ── wrap_words ──────────────────────────────────────────────────────────────


def test_wrap_words_respects_width_and_indent() -> None:
    text = "the quick brown fox jumps over the lazy dog " * 5
    lines = wrap_words(text, 20, indent="  ")
    assert all(len(line) <= 20 for line in lines)
    assert all(line.startswith("  ") for line in lines)
    assert " ".join(line.strip() for line in lines) == text.strip()


def test_wrap_words_long_word_gets_own_line_and_no_blank_lines() -> None:
    assert wrap_words("x " + "y" * 30 + " z", 10) == ["x", "y" * 30, "z"]
    assert wrap_words("", 10) == []


# ── BelAtro rules ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_rules_lines_cover_every_section_within_width(lang: str) -> None:
    from belote.belatro.ui.rules import BELATRO_RULES, rules_lines

    lines = rules_lines(lang, 60)
    joined = "\n".join(lines)
    for section in BELATRO_RULES[lang]["sections"]:
        assert section["header"] in joined
    body = [line for line in lines if line.startswith("  ")]
    assert body and all(visible_len(line) <= 60 for line in body)
    assert f"({lang.upper()})" in lines[-1]


# ── Collection gallery ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("n", "sel", "rows", "top"),
    [(5, 4, 10, 0), (30, 0, 10, 0), (30, 9, 10, 0), (30, 10, 10, 1), (30, 29, 10, 20)],
)
def test_collection_top_keeps_selection_visible(n: int, sel: int, rows: int, top: int) -> None:
    from belote.belatro.ui.collection import collection_top

    assert collection_top(n, sel, rows) == top
    assert top <= sel < top + rows


def _items(n: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id=f"i{k}", name=f"Item {k}", description="A fine item " * 6)
        for k in range(n)
    ]


def test_collection_frame_shows_rows_above_the_selection() -> None:
    """Pre-4.10.0 the list was sliced from the selected item, so moving down
    hid everything above it."""
    from belote.belatro.ui.collection import collection_frame

    cats = [("Jokers", _items(5)), ("Tarots", [])]
    frame = collection_frame(cats, {"i0", "i3"}, 0, 3, 100, 40)
    assert "Item 0" in frame  # above the selection, still listed
    assert "> Item 3" in frame
    assert "???" in frame  # undiscovered items are masked
    assert "COLLECTION - Jokers (2 Discovered)" in frame


def test_collection_frame_undiscovered_detail_and_empty_category() -> None:
    from belote.belatro.ui.collection import collection_frame

    frame = collection_frame([("Jokers", _items(2))], set(), 0, 0, 100, 40)
    assert "??? (Undiscovered)" in frame
    empty = collection_frame([("Tarots", [])], set(), 0, 0, 100, 40)
    assert "COLLECTION - Tarots" in empty


# ── Shop: scripted sessions through ShopScreen.run ─────────────────────────


class _Keys:
    def __init__(self, events: list[KeyEvent]) -> None:
        self._events: Iterator[KeyEvent] = iter(events)

    def read(self) -> KeyEvent:
        return next(self._events, KeyEvent(Key.EOF))

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        return None


@pytest.fixture
def quiet_shop(monkeypatch: pytest.MonkeyPatch) -> None:
    """No animations, a fixed terminal, no blocking banners, muted stdout."""
    import importlib

    from belote.belatro.ui import shop as shop_ui
    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.ui import anim, fit_guard

    render = importlib.import_module("belote.ui.render")
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    anim._refresh_animations_enabled_from_env()
    monkeypatch.setattr(render, "get_term_size", lambda: (120, 40))
    if hasattr(shop_ui, "get_term_size"):
        monkeypatch.setattr(shop_ui, "get_term_size", lambda: (120, 40))
    monkeypatch.setattr(fit_guard, "require_minimum", lambda reader: None)
    monkeypatch.setattr(BelAtroAnnounce, "banner", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    yield
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    anim._refresh_animations_enabled_from_env()


def _shop(money: int = 100):  # type: ignore[no-untyped-def]
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.run.shop import Shop

    register_all_items()
    run = BelAtroRun(seed=7)
    run.economy.money = money
    return Shop(run)


def test_shop_buy_first_item_spends_money(quiet_shop: None) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _shop()
    screen = ShopScreen(shop, _Keys([KeyEvent(Key.ENTER), KeyEvent(Key.ESC)]))  # type: ignore[arg-type]
    screen.run()
    assert shop.run.economy.money < 100
    owned = len(shop.run.jokers) + len(shop.run.consumables) + len(shop.run.vouchers)
    assert owned >= 1


def test_shop_reroll_charges_and_bumps_cost(quiet_shop: None) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _shop()
    screen = ShopScreen(shop, _Keys([]))  # type: ignore[arg-type]
    shop.generate_inventory()
    reroll_idx = len(shop.inventory)
    # Navigate left from 0 wraps to the last option; RIGHT n times lands on reroll.
    keys = [KeyEvent(Key.RIGHT)] * reroll_idx + [KeyEvent(Key.ENTER), KeyEvent(Key.QUIT)]
    screen = ShopScreen(shop, _Keys(keys))  # type: ignore[arg-type]
    cost = shop.reroll_cost
    screen.run()  # regenerates inventory, same size
    assert shop.run.economy.money <= 100 - cost
    assert shop.reroll_cost == cost + 1


def test_shop_sell_joker_via_overlay(quiet_shop: None) -> None:
    from belote.belatro.items.registry import registry
    from belote.belatro.ui.shop import ShopScreen

    shop = _shop(money=0)
    joker = next(cls() for cls in registry.jokers.values() if not getattr(cls, "corrupted", False))
    shop.run.jokers.append(joker)
    if not shop.can_sell(0):
        pytest.skip("first registry joker is unsellable")
    keys = [KeyEvent(Key.CHAR, "s"), KeyEvent(Key.CHAR, "1"), KeyEvent(Key.ESC)]
    ShopScreen(shop, _Keys(keys)).run()  # type: ignore[arg-type]
    assert shop.run.jokers == []
    assert shop.run.economy.money > 0


def test_shop_sell_with_no_jokers_and_eof_exit(quiet_shop: None) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _shop()
    ShopScreen(shop, _Keys([KeyEvent(Key.CHAR, "s")])).run()  # type: ignore[arg-type]
    assert shop.run.economy.money == 100  # nothing bought, EOF ends the loop
