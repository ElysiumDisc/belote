"""Scripted sessions through the BelAtro full-screen UIs: the main menu and
deck picker, the collection gallery, the rules pager and the [H] history."""

from __future__ import annotations

import pytest

from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.progression.save import Profile
from belote.belatro.run.decks import STARTING_DECKS
from belote.belatro.ui import history
from belote.belatro.ui.collection import show_collection
from belote.belatro.ui.history import BelAtroHistoryEntry, show_belatro_history
from belote.belatro.ui.menu import BelAtroMainMenu
from belote.belatro.ui.rules import BELATRO_RULES, show_belatro_rules
from belote.ui.fit_guard import FitAbortedError
from tests.harness import TUI

# ── BelAtro main menu ───────────────────────────────────────────────────────


def _menu(tui: TUI, *script: str) -> tuple[BelAtroMainMenu, object]:
    m = BelAtroMainMenu(tui.reader(*script).as_reader(), Profile())
    return m, m.run()


def test_menu_start_run_with_default_deck(tui: TUI) -> None:
    from belote.belatro.core.run_state import BelAtroRun

    m, run = _menu(tui, "enter")
    assert isinstance(run, BelAtroRun)
    assert run.deck_id == "classique"
    assert run.profile is m.profile
    for opt in (
        "Start Run",
        "Select Deck",
        "Boss Rush",
        "Watch Ghost Run",
        "Collection",
        "Rules",
        "Back",
    ):
        assert opt in tui.text
    assert "Deck: " + STARTING_DECKS[0].name in tui.text


@pytest.mark.parametrize(
    "script",
    [("esc",), ("q",), (), ("up", "enter"), ("down",) * 6 + ("enter",)],
    ids=["esc", "quit", "eof", "wrap-to-back", "back-entry"],
)
def test_menu_exits_without_a_run(tui: TUI, script: tuple[str, ...]) -> None:
    assert _menu(tui, *script)[1] is None


def test_menu_select_deck_then_start(tui: TUI) -> None:
    # Select Deck → down, down, up → deck #2 → Enter; back on menu: up → Start Run.
    m, run = _menu(tui, "down", "enter", "down", "down", "up", "enter", "up", "enter")
    assert run is not None
    assert m.selected_deck_id == STARTING_DECKS[1].id
    assert run.deck_id == STARTING_DECKS[1].id  # type: ignore[attr-defined]
    text = tui.text
    assert "Select Starting Deck" in text
    assert "Deck: " + STARTING_DECKS[1].name in text
    # The info panel shows the deck description (first few words at least).
    assert " ".join(STARTING_DECKS[1].description.split()[:2]) in text


@pytest.mark.parametrize("cancel", ["esc", "q", "eof"])
def test_menu_deck_picker_cancel_keeps_deck(tui: TUI, cancel: str) -> None:
    m = BelAtroMainMenu(tui.reader("down", "enter", "down", cancel, "esc").as_reader(), Profile())
    assert m.run() is None
    assert m.selected_deck_id == "classique"


def test_menu_deck_picker_wraps_both_ways(tui: TUI) -> None:
    # Up from the first deck wraps to the bottom; the last deck (Le Complice,
    # 4.11.0) is locked on a fresh profile, so Enter there is refused and a
    # second Up lands on the last unlocked one.
    m = BelAtroMainMenu(
        tui.reader("down", "enter", "up", "enter", "up", "enter", "esc").as_reader(), Profile()
    )
    m.run()
    assert not STARTING_DECKS[-1].is_unlocked(m.profile)
    assert m.selected_deck_id == STARTING_DECKS[-2].id
    assert "Defeat 5 Boss Blinds" in tui.text


def test_menu_deck_picker_narrow_terminal(tui: TUI) -> None:
    tui.resize(80, 32)
    m = BelAtroMainMenu(tui.reader("down", "enter", "down", "enter", "esc").as_reader(), Profile())
    m.run()
    assert m.selected_deck_id == STARTING_DECKS[1].id


def test_menu_opens_collection_and_rules(tui: TUI) -> None:
    register_all_items()
    _, run = _menu(tui, *("down",) * 4, "enter", "esc", "down", "enter", "esc", "esc")
    assert run is None
    assert "COLLECTION - Jokers" in tui.text
    assert BELATRO_RULES["en"]["title"].upper() in tui.text


def test_menu_too_small_terminal_quit_raises_fit_abort(tui: TUI) -> None:
    tui.resize(60, 20)
    with pytest.raises(FitAbortedError):
        _menu(tui, "q")
    assert "Terminal too small" in tui.text


def test_menu_waits_for_resize_then_renders(tui: TUI) -> None:
    # First polls are too small; the reader times out (None) and the next
    # poll sees the resized terminal.
    tui.term.queue_sizes((60, 20), (60, 20), (120, 40))
    _, run = _menu(tui, None, "esc")
    assert run is None
    assert "Terminal too small" in tui.text
    assert "Start Run" in tui.text


# ── Collection ──────────────────────────────────────────────────────────────


@pytest.fixture
def profile() -> Profile:
    register_all_items()
    p = Profile()
    p.discovered_items = [next(iter(registry.jokers)), next(iter(registry.tarots))]
    return p


def test_collection_browse_categories_and_items(tui: TUI, profile: Profile) -> None:
    first_joker = next(iter(registry.jokers.values()))
    # 5.0.0: Recipes and Médailles sit between Jokers and Tarots.
    r = tui.reader("down", "down", "up", *["right"] * 6, "left", "q")
    show_collection(r.as_reader(), profile)
    assert r.exhausted
    text = tui.text
    for cat in ("Jokers", "Recipes", "Médailles", "Tarots", "Planets", "Vouchers"):
        assert f"COLLECTION - {cat} (2 Discovered)" in text
    assert first_joker.name in text
    assert "??? (Undiscovered)" in text
    assert "Keep playing to find this item!" in text


def test_collection_item_cursor_is_clamped(tui: TUI, profile: Profile) -> None:
    n = len(registry.jokers)
    r = tui.reader(*["down"] * (n + 5), "up", "esc")
    show_collection(r.as_reader(), profile)
    last_frame = tui.screen.frames()[-1]
    # After clamping at the end and one UP, the cursor sits on item n-2.
    assert last_frame.count("> ") == 1


@pytest.mark.parametrize("exit_key", ["esc", "q", "eof"])
def test_collection_exit_keys(tui: TUI, profile: Profile, exit_key: str) -> None:
    r = tui.reader(exit_key, "down")
    show_collection(r.as_reader(), profile)
    assert r.remaining == 1


def test_collection_empty_category_is_safe(
    tui: TUI, profile: Profile, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "vouchers", {})
    # Jokers → (wrap) Bosses → Vouchers (empty)
    r = tui.reader("left", "left", "down", "up", "esc")
    show_collection(r.as_reader(), profile)
    assert "COLLECTION - Vouchers" in tui.text


# ── Rules pager ─────────────────────────────────────────────────────────────


def test_rules_scroll_toggle_language_and_back(tui: TUI) -> None:
    tui.resize(100, 32)
    r = tui.reader("down", "down", "up", "x", "l", "down", "L", "esc")
    show_belatro_rules(r.as_reader())
    assert r.exhausted
    text = tui.text
    assert BELATRO_RULES["en"]["title"].upper() in text
    assert BELATRO_RULES["fr"]["title"].upper() in text


@pytest.mark.parametrize("exit_key", ["q", "enter", "esc", "eof"])
def test_rules_exit_keys(tui: TUI, exit_key: str) -> None:
    r = tui.reader(exit_key, "down")
    show_belatro_rules(r.as_reader())
    assert r.remaining == 1


def test_rules_scroll_clamped_at_both_ends(tui: TUI) -> None:
    tui.resize(90, 32)
    r = tui.reader(*["down"] * 300, "q")
    show_belatro_rules(r.as_reader())
    frames = tui.screen.frames()
    assert frames[-1] == frames[-2]  # pinned at max scroll
    tui.screen.clear()
    show_belatro_rules(tui.reader("up", "up", "q").as_reader())
    frames = tui.screen.frames()
    assert frames[0] == frames[1] == frames[2]  # pinned at the top


def test_rules_footer_reachable_by_scrolling(tui: TUI) -> None:
    tui.resize(90, 32)
    show_belatro_rules(tui.reader(*["down"] * 300, "q").as_reader())
    assert "Toggle Language (EN)" in tui.text


# ── History overlay ─────────────────────────────────────────────────────────


def _entry(**kw: object) -> BelAtroHistoryEntry:
    base: dict[str, object] = {
        "ante": 1,
        "blind_label": "Small",
        "target": 300,
        "boss_name": None,
        "taker_label": "S (NS)",
        "contract": "♥",
        "tricks_ns": 5,
        "tricks_ew": 3,
        "score": 420,
        "status": "WON",
        "money_delta": 6,
        "decl_summary_ns": (),
        "decl_summary_ew": (),
    }
    base.update(kw)
    return BelAtroHistoryEntry(**base)  # type: ignore[arg-type]


ENTRIES = [
    _entry(),
    _entry(blind_label="Big", status="FAILED", money_delta=-3, decl_summary_ns=("Tierce",)),
    _entry(
        blind_label="Boss",
        boss_name="L'Extraordinairement Long Boss",
        status="CAPOT",
        money_delta=0,
        decl_summary_ew=("Cinquante", "Carré de valets", "Belote et rebelote"),
    ),
    _entry(ante=2, status="SURVIVED", taker_label="—", contract="SA"),
    _entry(ante=2, status=""),
]


def test_history_wide_layout(tui: TUI) -> None:
    r = tui.reader("down", "up", "x")
    show_belatro_history(r.as_reader(), ENTRIES)
    text = tui.text
    assert "BELATRO RUN HISTORY" in text
    assert "BOSS" in text and "$Δ" in text
    for status in ("WON", "FAILED", "CAPOT", "SURVIVED"):
        assert status in text
    assert "+$6" in text and "-$3" in text and "$0" in text
    assert "L'Extraordina…" in text  # 14-cell boss column truncation
    assert "—" in text  # empty status renders as an em dash


def test_history_narrow_layout_three_lines_per_entry(tui: TUI) -> None:
    tui.resize(90, 40)
    show_belatro_history(tui.reader("q").as_reader(), ENTRIES)
    text = tui.text
    assert "A.B" in text
    assert "1.S" in text and "1.B" in text
    assert "boss: L'Extraordinairement Long Boss" in text
    assert "decl: Tierce / ─" in text
    assert "Cinquante Car…" in text  # decl column truncation at 14


def test_history_empty(tui: TUI) -> None:
    show_belatro_history(tui.reader().as_reader(), [])
    assert "No blinds completed yet." in tui.text


def test_history_scroll_clamped_and_cache_reused(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> None:
    builds: list[int] = []
    real = history._build_history_lines

    def spy(entries: list[BelAtroHistoryEntry], term_w: int) -> list[str]:
        builds.append(term_w)
        return real(entries, term_w)

    monkeypatch.setattr(history, "_build_history_lines", spy)
    tui.resize(90, 32)
    r = tui.reader(*["down"] * 80, *["up"] * 90, "enter")
    show_belatro_history(r.as_reader(), ENTRIES * 4)
    assert builds == [90]  # built once despite 170 scroll keystrokes
    frames = tui.screen.frames()
    assert frames[80] == frames[79]  # bottom clamp
    assert frames[-1] == frames[0]  # back at the top


def test_history_rebuilds_on_resize(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> None:
    builds: list[int] = []
    real = history._build_history_lines
    monkeypatch.setattr(
        history, "_build_history_lines", lambda e, w: builds.append(w) or real(e, w)
    )
    # require_minimum polls once and get_term_size once per frame.
    tui.term.queue_sizes((120, 40), (120, 40), (100, 40), (100, 40))
    show_belatro_history(tui.reader("down", "x").as_reader(), ENTRIES)
    assert builds == [120, 100]
