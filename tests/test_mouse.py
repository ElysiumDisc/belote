"""5.0.0 mouse support: SGR report parsing in the Unix reader, the hit map,
clicking cards in `prompt_card` and offers / buttons in the BelAtro shop."""

from __future__ import annotations

import types
from collections.abc import Iterator
from typing import Any

import pytest

import belote.input as inp
from belote.input import Key, KeyEvent, _UnixKeyReader, parse_sgr_mouse
from belote.ui import hitmap
from tests.test_input_reader import FakeStdin


@pytest.fixture
def stdin(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeStdin]:
    fake = FakeStdin()
    monkeypatch.setattr(inp, "os", types.SimpleNamespace(read=fake.read, name="posix"))
    monkeypatch.setattr(inp, "select", types.SimpleNamespace(select=fake.select))
    yield fake


def _reader() -> _UnixKeyReader:
    r = _UnixKeyReader.__new__(_UnixKeyReader)
    r._old_termios = None
    r._stdin_fd = 0
    r._restored = False
    return r


# ── parsing ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("params", "final", "expected"),
    [
        (b"0;10;5", b"M", KeyEvent(Key.MOUSE, pos=(10, 5))),
        (b"16;3;4", b"M", KeyEvent(Key.MOUSE, pos=(3, 4))),  # Ctrl-click still clicks
        (b"0;10;5", b"m", None),  # release
        (b"32;10;5", b"M", None),  # motion
        (b"2;10;5", b"M", None),  # right button
        (b"64;1;1", b"M", KeyEvent(Key.UP)),  # wheel
        (b"65;1;1", b"M", KeyEvent(Key.DOWN)),
        (b"0;x;5", b"M", None),  # malformed
        (b"0;10", b"M", None),
    ],
)
def test_parse_sgr_mouse(params: bytes, final: bytes, expected: KeyEvent | None) -> None:
    assert parse_sgr_mouse(params, final) == expected


def test_reader_reads_a_click_and_skips_its_release(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"\x1b[<0;12;7M\x1b[<0;12;7m\r"
    r = _reader()
    assert r.read() == KeyEvent(Key.MOUSE, pos=(12, 7))
    assert r.read() == KeyEvent(Key.ENTER)  # the release never surfaces


def test_read_timeout_ignores_a_lone_release(stdin: FakeStdin) -> None:
    stdin.buf[:] = b"\x1b[<0;1;1m"
    assert _reader().read_timeout(0.05) is None


def test_mouse_reporting_follows_the_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from belote.ansi import mouse_off, mouse_on

    r = _reader()
    r._old_termios = [0]  # a real terminal
    monkeypatch.setattr(inp, "_active_unix_reader", r)
    inp.set_mouse_enabled(True)
    inp.set_mouse_enabled(True)  # no repeat
    inp.set_mouse_enabled(False)
    assert capsys.readouterr().out == mouse_on() + mouse_off()
    inp.set_mouse_enabled(True)
    capsys.readouterr()
    assert inp.mouse_enabled()


def test_settings_toggle_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.settings import Settings

    s = Settings()
    assert s.mouse_on()
    monkeypatch.setenv("BELOTE_NO_MOUSE", "1")
    assert not s.mouse_on()


# ── hit map ─────────────────────────────────────────────────────────────────


def test_hitmap_regions() -> None:
    hitmap.set_regions("t", [hitmap.Region(2, 3, 2, 4, "a"), hitmap.Region(3, 5, 1, 1, "b")])
    assert hitmap.hit("t", (3, 2)) == "a"
    assert hitmap.hit("t", (6, 3)) == "a"
    assert hitmap.hit("t", (5, 3)) == "b"  # later region on top
    assert hitmap.hit("t", (7, 2)) is None
    assert hitmap.hit("t", None) is None
    hitmap.clear("t")
    assert hitmap.hit("t", (3, 2)) is None


# ── clicking cards ──────────────────────────────────────────────────────────


def _playing_state() -> Any:
    import random
    from dataclasses import replace

    from belote.deck import Suit
    from belote.game import Phase, Seat, new_game, start_round

    state = start_round(new_game(), random.Random(3))
    hands = list(state.hands)
    return replace(
        state,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
        leader=Seat.SOUTH,
        trump=Suit.HEARTS,
        contract="normal",
        taker=Seat.SOUTH,
        hands=tuple(hands),
    )


def _card_center(index: int) -> tuple[int, int]:
    region = next(r for r in hitmap._regions["hand"] if r.target == index)
    return region.col + 1, region.row + 1


@pytest.mark.parametrize("size", [(80, 24), (100, 40), (140, 50)])
def test_hand_regions_sit_on_the_drawn_cards(tui: Any, size: tuple[int, int]) -> None:
    import sys

    import belote.ui.render  # noqa: F401 — `belote.ui.render` is shadowed by a function
    from belote.game import Seat
    from belote.ui.layout import fit_table

    render_mod = sys.modules["belote.ui.render"]
    from tests.harness import strip_ansi

    tui.resize(*size)
    state = _playing_state()
    render_mod.render(state, 2)
    rows = [strip_ansi(line) for line in render_mod._pending_rendered_lines or ()]
    regions = hitmap._regions["hand"]
    hand = state.hand_of(Seat.SOUTH)
    assert [r.target for r in regions] == list(range(len(hand)))
    card_w = regions[0].width - fit_table(size[0], size[1]).layout.card_gap
    for region, card in zip(regions, hand, strict=True):
        # The card's face (rank symbol) is printed inside its region, on
        # one of its rows — so a click there hits that card and no other.
        cells = [
            rows[r - 1][region.col - 1 : region.col - 1 + card_w]
            for r in range(region.row, region.row + region.height)
        ]
        assert any(card.rank.value in c for c in cells), (card, cells)


def test_click_selects_then_plays_a_card(tui: Any) -> None:
    from belote.game import Seat, legal_cards
    from belote.ui.prompts import prompt_card
    from belote.ui.render import display

    tui.resize(100, 40)
    state = _playing_state()
    from belote.game.sorting import sort_south_hand

    sorted_state = sort_south_hand(state)
    display(sorted_state, 0)  # records the hand's regions at this size
    hand = sorted_state.hand_of(Seat.SOUTH)
    legal = legal_cards(sorted_state, Seat.SOUTH)
    target = max(i for i, c in enumerate(hand) if c in legal)
    click = KeyEvent(Key.MOUSE, pos=_card_center(target))
    card, _ = prompt_card(state, tui.reader(click, click))
    assert card == hand[target]


def test_click_outside_the_hand_does_nothing(tui: Any) -> None:
    from belote.ui.prompts import prompt_card

    tui.resize(100, 40)
    card, _ = prompt_card(_playing_state(), tui.reader(KeyEvent(Key.MOUSE, pos=(1, 1)), "q"))
    assert card is None


# ── clicking in the shop ────────────────────────────────────────────────────


def test_shop_click_selects_then_buys(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.jokers.tempo import LeCapitaine, LeMarechal
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.run.shop import Shop
    from belote.belatro.ui.shop import ShopScreen

    register_all_items()
    run = BelAtroRun(seed=1)
    run.economy.money = 50
    run.jokers.clear()
    shop = Shop(run)
    inv = [LeCapitaine(), LeMarechal()]
    monkeypatch.setattr(shop, "generate_inventory", lambda: setattr(shop, "inventory", list(inv)))

    class Clicks:
        """Click the second card (twice) once the first frame recorded it."""

        def __init__(self) -> None:
            self.n = 0

        def read(self) -> KeyEvent:
            self.n += 1
            if self.n <= 2:
                region = next(r for r in hitmap._regions["shop"] if r.target == ("item", 1))
                return KeyEvent(Key.MOUSE, pos=(region.col + 2, region.row + 1))
            return KeyEvent(Key.ESC)

        def read_timeout(self, _t: float) -> None:
            return None

    ShopScreen(shop, Clicks()).run()  # type: ignore[arg-type]
    assert [j.id for j in run.jokers] == ["le_marechal"]


def test_shop_click_presses_an_action_button(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.run.shop import Shop
    from belote.belatro.ui.shop import ShopScreen

    register_all_items()
    run = BelAtroRun(seed=1)
    run.economy.money = 50
    shop = Shop(run)
    rolls: list[int] = []
    monkeypatch.setattr(
        shop, "generate_inventory", lambda: (rolls.append(1), setattr(shop, "inventory", []))
    )

    class Clicks:
        n = 0

        def read(self) -> KeyEvent:
            self.n += 1
            if self.n == 1:
                region = next(r for r in hitmap._regions["shop"] if r.target == ("action", 0))
                return KeyEvent(Key.MOUSE, pos=(region.col, region.row))
            return KeyEvent(Key.ESC)

        def read_timeout(self, _t: float) -> None:
            return None

    ShopScreen(shop, Clicks()).run()  # type: ignore[arg-type]
    # Empty shop → Reroll is already selected, so one click presses it.
    assert len(rolls) == 2 and run.economy.money == 45


# ── bid selector, menus, prompts ────────────────────────────────────────────


class LazyClicks:
    """A reader whose steps are KeyEvents or (namespace, target) clicks
    resolved against the live hit map when read — i.e. on the frame the
    screen just painted. EOF once the script runs out."""

    def __init__(self, *steps: Any) -> None:
        self.steps = list(steps)

    def _next(self) -> KeyEvent:
        if not self.steps:
            return KeyEvent(Key.EOF)
        step = self.steps.pop(0)
        if isinstance(step, KeyEvent):
            return step
        namespace, target = step
        region = next(r for r in hitmap._regions[namespace] if r.target == target)
        return KeyEvent(Key.MOUSE, pos=(region.col + min(1, region.width - 1), region.row))

    def read(self) -> KeyEvent:
        return self._next()

    def read_timeout(self, _t: float) -> KeyEvent:
        return self._next()


def test_targets_from_lines_searches_in_order() -> None:
    lines = ["\x1b[1mTitle\x1b[0m", "  Start  ", "  Back  ", "Hint: Back / Start", "[Y]es / [N]o"]
    labels = [("Start", 0), ("Back", 1), ("[Y]es", 2), ("[N]o", 3)]
    hitmap.targets_from_lines("t", lines, labels, first_row=5)
    by_target = {r.target: r for r in hitmap._regions["t"]}
    assert (by_target[0].row, by_target[1].row) == (6, 7)  # not the hint row
    assert by_target[1].col == 1 and by_target[1].width == len("Back") + 4
    assert by_target[2].row == by_target[3].row == 9  # two choices on one line
    assert by_target[3].col > by_target[2].col
    hitmap.targets_from_lines("t", lines, [("Back", "b")], full_row=True)
    assert hitmap.hit("t", (999, 3)) == "b"  # default first_row=1


def _bidding_state(round_no: int) -> Any:
    import random
    from dataclasses import replace

    from belote.game import Phase, Seat, new_game, start_round

    state = start_round(new_game(), random.Random(5))
    return replace(state, phase=Phase.BIDDING, turn=Seat.SOUTH, bidding_round=round_no)


@pytest.mark.parametrize("round_no", [1, 2])
@pytest.mark.parametrize("size", [(80, 24), (120, 45)])
def test_bid_regions_sit_on_the_drawn_options(
    tui: Any, round_no: int, size: tuple[int, int]
) -> None:
    import sys

    import belote.ui.render  # noqa: F401 — shadowed by a function
    from belote.game import legal_bids
    from tests.harness import strip_ansi

    render_mod = sys.modules["belote.ui.render"]
    tui.resize(*size)
    state = _bidding_state(round_no)
    for sel in range(len(legal_bids(state))):
        render_mod.render(state, None, bid_selection=sel)
        rows = [strip_ansi(line) for line in render_mod._pending_rendered_lines or ()]
        regions = hitmap._regions["bid"]
        assert [r.target for r in regions] == list(range(len(legal_bids(state))))
        for r in regions:
            cell = rows[r.row - 1][r.col - 1 : r.col - 1 + r.width]
            assert f"({r.target + 1})" in cell, (sel, r, cell)


def test_click_selects_then_bids(tui: Any) -> None:
    from belote.game import legal_bids
    from belote.ui.prompts import prompt_bid

    tui.resize(100, 40)
    state = _bidding_state(2)
    last = len(legal_bids(state)) - 1
    assert prompt_bid(state, LazyClicks(("bid", last), ("bid", last))) == legal_bids(state)[last]


def test_main_menu_click_picks_an_entry(tui: Any) -> None:
    from belote.ui.menu import show_main_menu

    for size in ((80, 24), (120, 60)):  # compact menu and the full cup art
        tui.resize(*size)
        assert show_main_menu(LazyClicks(("menu", 2)), ("BelAtro",)) == "Hot-seat & Spectate"


def test_picker_click(tui: Any) -> None:
    from belote.ui.picker import pick_option

    assert pick_option(LazyClicks(("menu", 2)), "Pick", ["a", "b", "c"]) == 2


def test_settings_click_selects_then_toggles(tui: Any) -> None:
    from belote.settings import Settings
    from belote.ui.settings_menu import rows, show_settings

    tui.resize(100, 45)
    s = Settings()
    idx = next(i for i, r in enumerate(rows()) if r.key == "animations")
    show_settings(LazyClicks(("menu", idx), ("menu", idx), KeyEvent(Key.ESC)), s)
    assert s.animations is False


def test_ai_config_click_steps_a_seat(tui: Any) -> None:
    from belote.game import Seat
    from belote.ui.menu import show_ai_config

    diffs = {Seat.EAST: "easy", Seat.NORTH: "easy", Seat.WEST: "easy"}
    out = show_ai_config(LazyClicks(("menu", 1), ("menu", 1), KeyEvent(Key.ESC)), diffs)
    assert out[Seat.NORTH] == "medium" and out[Seat.EAST] == "easy"


def test_theme_selector_click(tui: Any) -> None:
    from belote.themes import THEMES, theme_manager
    from belote.ui.menu import show_theme_selector

    before = theme_manager.current_name
    keys = list(THEMES)
    target = (keys.index(before) + 1) % len(keys)
    try:
        show_theme_selector(LazyClicks(("menu", target), ("menu", target)))
        assert theme_manager.current_name == keys[target]
    finally:
        theme_manager.set_current(before)


def test_belatro_menu_and_deck_picker_clicks(tui: Any) -> None:
    from belote.belatro.progression.save import Profile
    from belote.belatro.run.decks import STARTING_DECKS
    from belote.belatro.ui.menu import BelAtroMainMenu

    tui.resize(100, 40)
    profile = Profile()
    unlocked = [i for i, d in enumerate(STARTING_DECKS) if d.is_unlocked(profile)]
    deck = unlocked[-1]
    menu = BelAtroMainMenu(LazyClicks(), profile)  # type: ignore[arg-type]
    menu.reader = LazyClicks(  # type: ignore[assignment]
        ("menu", 1),  # Select Deck
        ("menu", deck),
        ("menu", deck),
        ("menu", 0),  # Start Run
    )
    run = menu.run()
    assert run is not None and run.deck_id == STARTING_DECKS[deck].id


def test_yes_no_and_coinche_clicks(tui: Any) -> None:
    from dataclasses import replace

    from belote.belatro.ui.announce import BelAtroAnnounce
    from belote.game import Seat, new_game
    from belote.ui.prompts import prompt_coinche, prompt_surcoinche

    assert BelAtroAnnounce.yes_no("Sure?", LazyClicks(("choice", False))) is False  # type: ignore[arg-type]
    assert BelAtroAnnounce.yes_no("Sure?", LazyClicks(("choice", True))) is True  # type: ignore[arg-type]
    state = replace(new_game(), taker=Seat.EAST)
    assert prompt_coinche(state, LazyClicks(("choice", True))) is True  # type: ignore[arg-type]
    assert prompt_coinche(state, LazyClicks(("choice", False))) is False  # type: ignore[arg-type]
    assert prompt_surcoinche(LazyClicks(("choice", True)), "EW") is True  # type: ignore[arg-type]


@pytest.mark.parametrize("size", [(80, 24), (100, 40), (120, 45), (160, 70)])
def test_round_two_bid_options_are_always_on_screen(tui: Any, size: tuple[int, int]) -> None:
    """The round-2 box (7 rows) used to be clipped off the bottom with its
    options at most sizes; it now falls back to the one-line selector."""
    import sys

    import belote.ui.render  # noqa: F401 — shadowed by a function
    from belote.game import legal_bids
    from tests.harness import strip_ansi

    render_mod = sys.modules["belote.ui.render"]
    tui.resize(*size)
    state = _bidding_state(2)
    render_mod.render(state, None, bid_selection=0)
    rows = [strip_ansi(line) for line in render_mod._pending_rendered_lines or ()]
    assert len(rows) <= size[1]
    for i in range(len(legal_bids(state))):
        assert any(f"({i + 1})" in r for r in rows), (size, i)


# ── remaining screens: Settings sub-screens, Collection, Boss Rush, rules,
#    ghost runs ───────────────────────────────────────────────────────────


def test_cosmetic_picker_click_selects_then_chooses(tui: Any) -> None:
    from belote import cosmetics
    from belote.cosmetics import CardBack
    from belote.settings import Settings
    from belote.ui.customize import show_cosmetic_picker

    tui.resize(100, 50)
    items = list(cosmetics.CARD_BACKS.values())
    earned = cosmetics.load_unlocked()
    free = next(i for i, b in enumerate(items[1:], 1) if cosmetics.is_unlocked(b, earned))
    locked = next(i for i, b in enumerate(items) if not cosmetics.is_unlocked(b, earned))
    s = Settings()
    clicks = [("menu", locked)] * 2 + [("menu", free)] * 2 + [KeyEvent(Key.ESC)]
    show_cosmetic_picker(LazyClicks(*clicks), s, CardBack)
    assert "Locked" in tui.text  # the locked back explained itself
    assert s.card_back == items[free].id  # the unlocked one was chosen


def test_controls_click_reset_and_back(tui: Any) -> None:
    from belote.input import BINDINGS
    from belote.settings import Settings
    from belote.ui.customize import show_controls

    tui.resize(100, 45)
    s = Settings(keys={"sort": "y"})
    reset, back = len(BINDINGS), len(BINDINGS) + 1
    show_controls(LazyClicks(("menu", reset), ("menu", reset), ("menu", back), ("menu", back)), s)
    assert s.keys == {} and "All keys reset to defaults" in tui.text


def test_theme_files_click_export(tui: Any) -> None:
    from belote.ui.customize import show_theme_files

    tui.resize(100, 40)
    show_theme_files(LazyClicks(("menu", 0), ("menu", 1), ("menu", 1)))
    assert "Exported to" in tui.text


def test_collection_click_tab_and_item(tui: Any) -> None:
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.progression.save import Profile
    from belote.belatro.ui.collection import collection_categories, show_collection

    register_all_items()
    tui.resize(110, 40)
    profile = Profile()
    tarots = [name for name, _ in collection_categories(profile)[0]].index("Tarots")
    show_collection(LazyClicks(("menu", ("tab", tarots)), ("menu", ("item", 2))), profile)
    frames = tui.screen.take()
    assert "COLLECTION - Tarots" in frames
    last = frames.rsplit("COLLECTION - Tarots", 1)[1]
    assert last.count("> ") == 1


def test_boss_rush_click_steps_and_starts(tui: Any) -> None:
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.progression.save import Profile
    from belote.belatro.ui.boss_rush import show_boss_rush

    register_all_items()
    tui.resize(100, 40)
    step = ("menu", ("step", 0, +1))
    run = show_boss_rush(LazyClicks(step, step, ("menu", ("start", 5))), Profile())
    assert run is not None and run.ante_number == 3


def test_rules_footer_clicks(tui: Any) -> None:
    from belote.belatro.ui.rules import show_belatro_rules
    from belote.ui.prompts import show_rules

    tui.resize(100, 34)
    down = [KeyEvent(Key.DOWN)] * 200  # scroll to the footer
    show_belatro_rules(LazyClicks(*down, ("menu", "lang"), *down, ("menu", "back")))
    assert "Toggle Language (FR)" in tui.text  # the click switched to French
    show_rules(LazyClicks(*down, ("menu", "lang"), *down, ("menu", "back")))


def test_ghost_picker_click_watches(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import belote.belatro.ghost_run as ghost_run
    from belote.belatro.ui import ghost_viewer

    ghosts = [
        types.SimpleNamespace(summary="Run one — seed 1"),
        types.SimpleNamespace(summary="Run two — seed 2"),
    ]
    watched: list[object] = []
    monkeypatch.setattr(ghost_run, "load_all_ghosts", lambda: ghosts)
    monkeypatch.setattr(ghost_viewer, "watch_ghost", lambda g, r: watched.append(g))
    ghost_viewer.show_ghost_picker(LazyClicks(("menu", 1), KeyEvent(Key.ESC)))  # type: ignore[arg-type]
    assert watched == [ghosts[1]]


def test_ghost_viewer_click_toggles_pause() -> None:
    from belote.belatro.ui.ghost_viewer import ReplayControl, control_action

    ctl = ReplayControl()
    assert control_action(KeyEvent(Key.MOUSE, pos=(1, 1)), ctl) == "stay" and ctl.paused
    assert control_action(KeyEvent(Key.MOUSE, pos=(1, 1)), ctl) == "next" and not ctl.paused
