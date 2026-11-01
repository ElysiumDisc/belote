"""Scripted sessions through the classic main menu, theme selector, AI
configuration, the Settings screen and the `belote.main` application loop."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import Any

import pytest

import belote.main as main_mod
from belote import settings as settings_mod
from belote.game import GameState, Phase, Seat, new_game
from belote.settings import Settings, Toggle
from belote.themes import THEMES, theme_manager
from belote.ui import menu, settings_menu
from tests.harness import TUI, ScriptedReader

_CORE = list(menu.CORE_MENU_ENTRIES)

# ── show_main_menu ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (("enter",), "Start Game"),
        (("down", "enter"), "Hot-seat & Spectate"),
        (("down", "down", "enter"), "Settings"),
        (("down",) * 4 + ("enter",), "Statistics"),
        (("up", "enter"), "Quit"),  # wraps from the top
        (("down",) * len(_CORE) + ("enter",), "Start Game"),  # wraps from the bottom
        (("q",), "Quit"),
        (("ctrl-c",), "Quit"),
        ((), "Quit"),  # EOF
    ],
)
def test_main_menu_selection(tui: TUI, script: tuple[str, ...], expected: str) -> None:
    assert menu.show_main_menu(tui.reader(*script).as_reader()) == expected


def test_main_menu_modes_come_first(tui: TUI) -> None:
    r = tui.reader("down", "enter")
    assert menu.show_main_menu(r.as_reader(), ["BelAtro", "Daily"]) == "Daily"
    for label in ("BelAtro", "Daily", *_CORE):
        assert label in tui.text
    assert "> Daily <" in tui.text


def test_main_menu_idle_ticks_animate_steam(tui: TUI) -> None:
    # None = read_timeout timed out → next steam frame, then select.
    r = tui.reader(None, None, None, "enter")
    assert menu.show_main_menu(r.as_reader()) == "Start Game"
    assert r.timeouts == [0.3] * 4
    frames = tui.screen.raw.count("\x1b[1;1H")
    assert frames == 4


def test_main_menu_help_theme_and_unbound_keys(tui: TUI) -> None:
    before = theme_manager.current_name
    r = tui.reader("?", "space", "t", "unknown", "x", "esc", "enter")
    assert menu.show_main_menu(r.as_reader()) == "Start Game"
    assert theme_manager.current_name != before
    assert "KEYBOARD SHORTCUTS" in tui.text


def test_main_menu_croissant_art_only_on_tall_terminals(tui: TUI) -> None:
    croissant = "⣿⣿⣿⣿⣿⣿⣦"
    tui.resize(120, 60)
    menu.show_main_menu(tui.reader("q").as_reader())
    assert croissant in tui.screen.take()
    tui.resize(120, 34)
    menu.show_main_menu(tui.reader("q").as_reader())
    text = tui.screen.take()
    assert croissant not in text
    assert "Start Game" in text


# ── theme selector ──────────────────────────────────────────────────────────


def test_theme_selector_previews_live_and_keeps_choice(tui: TUI) -> None:
    names = list(THEMES)
    start = names.index(theme_manager.current_name)
    r = tui.reader("down", "down", "up", "down", "enter")
    menu.show_theme_selector(r.as_reader())
    assert theme_manager.current_name == names[(start + 2) % len(names)]
    assert "SELECT THEME" in tui.text
    for t in THEMES.values():
        assert t.name in tui.text


@pytest.mark.parametrize("exit_key", ["esc", "q", "eof"])
def test_theme_selector_exit_keys(tui: TUI, exit_key: str) -> None:
    r = tui.reader(exit_key, "down")
    menu.show_theme_selector(r.as_reader())
    assert r.remaining == 1


def test_theme_selector_unknown_current_theme_starts_at_first(
    tui: TUI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(theme_manager, "_current_theme_name", "no-such-theme")
    menu.show_theme_selector(tui.reader("enter").as_reader())
    assert theme_manager.current_name == next(iter(THEMES))


# ── AI configuration ────────────────────────────────────────────────────────


def _diffs() -> dict[Seat, str]:
    return {Seat.EAST: "medium", Seat.NORTH: "medium", Seat.WEST: "medium"}


def test_ai_config_changes_each_seat(tui: TUI) -> None:
    # East → hard; North → easy; West: right, right → easy (wraps past hard).
    r = tui.reader("right", "down", "left", "down", "right", "right", "enter")
    out = menu.show_ai_config(r.as_reader(), _diffs())
    assert out == {Seat.EAST: "hard", Seat.NORTH: "easy", Seat.WEST: "easy"}
    assert "AI CONFIGURATION" in tui.text
    assert "East: < Hard >" in tui.text


def test_ai_config_up_wraps_and_invalid_value_resets(tui: TUI) -> None:
    diffs = _diffs()
    diffs[Seat.WEST] = "godlike"
    r = tui.reader("up", "right", "esc")
    out = menu.show_ai_config(r.as_reader(), diffs)
    assert out[Seat.WEST] == "medium"


@pytest.mark.parametrize("exit_key", ["esc", "q", "eof", "enter"])
def test_ai_config_exit_keys_return_current(tui: TUI, exit_key: str) -> None:
    diffs = _diffs()
    assert menu.show_ai_config(tui.reader(exit_key).as_reader(), diffs) is diffs


def test_ai_config_help(tui: TUI) -> None:
    menu.show_ai_config(tui.reader("?", "x", "esc").as_reader(), _diffs())
    assert "KEYBOARD SHORTCUTS" in tui.text


# ── Settings screen ─────────────────────────────────────────────────────────


@pytest.fixture
def saves(monkeypatch: pytest.MonkeyPatch) -> list[Settings]:
    out: list[Settings] = []
    monkeypatch.setattr(settings_mod, "save", out.append)
    return out


def _row(key: str) -> int:
    return [r.key for r in settings_menu.rows()].index(key)


def test_settings_up_wraps_to_back_and_enter_closes(tui: TUI, saves: list[Settings]) -> None:
    s = Settings()
    r = tui.reader("up", "enter", "down")
    settings_menu.show_settings(r.as_reader(), s)
    assert r.remaining == 1
    assert saves == [s]


def test_settings_toggle_rows_with_enter_and_arrows(tui: TUI, saves: list[Settings]) -> None:
    s = Settings()
    anim_row = _row("animations")
    r = tui.reader(*["down"] * anim_row, "enter", "down", "left", "unknown", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.animations is False
    assert s.fast_redraw is False
    assert settings_mod.current() is s
    assert "SETTINGS" in tui.text and "Animations" in tui.text


def test_settings_enter_on_ai_opens_per_seat_config(tui: TUI, saves: list[Settings]) -> None:
    s = Settings()
    # ENTER on the AI row → AI config: East right (hard), Enter back; Esc.
    r = tui.reader("enter", "right", "enter", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.ai == {"east": "hard", "north": "medium", "west": "medium"}
    assert "Mixed" in tui.text


def test_settings_enter_on_theme_opens_selector(tui: TUI, saves: list[Settings]) -> None:
    names = list(THEMES)
    start = names.index(theme_manager.current_name)
    r = tui.reader(*["down"] * _row("theme"), "enter", "down", "enter", "esc")
    settings_menu.show_settings(r.as_reader(), Settings())
    assert theme_manager.current_name == names[(start + 1) % len(names)]
    assert "SELECT THEME" in tui.text


def test_settings_extra_toggle_row(
    tui: TUI, saves: list[Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(settings_mod.TOGGLES, "zz_test", Toggle("zz_test", "ZZ toggle", False))
    s = Settings()
    r = tui.reader(*["down"] * _row("extra:zz_test"), "enter", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.extras["zz_test"] is True
    assert "ZZ toggle" in tui.text


def test_settings_saves_even_on_eof(tui: TUI, saves: list[Settings]) -> None:
    s = Settings(target=1500)
    settings_menu.show_settings(tui.reader().as_reader(), s)
    assert saves == [s]


# ── belote.main application loop ────────────────────────────────────────────


class App:
    """Patches `belote.main` collaborators and records what the loop does."""

    def __init__(self, tui: TUI, monkeypatch: pytest.MonkeyPatch, reader: ScriptedReader) -> None:
        self.tui = tui
        self.reader = reader
        self.calls: list[str] = []
        self.handlers: dict[int, Any] = {}
        self.atexit: list[Any] = []
        self.rounds: list[GameState] = []
        self.round_results: list[GameState | BaseException | None] = []
        self.ai_diffs: dict[Seat, str] = {}
        self.toasts: list[Any] = []
        self.unlocked: list[Any] = []
        self.stats_games: list[dict[str, Any]] = []
        mp = monkeypatch
        mp.setattr(main_mod, "KeyReader", lambda: reader)
        mp.setattr(main_mod.signal, "signal", lambda sig, h: self.handlers.__setitem__(sig, h))
        mp.setattr(main_mod.atexit, "register", self.atexit.append)
        mp.setattr(main_mod, "flush_stats", lambda: self.calls.append("flush"))
        mp.setattr(main_mod, "show_settings", lambda r, p: self.calls.append("settings"))
        mp.setattr(main_mod, "show_rules", lambda r: self.calls.append("rules"))
        mp.setattr(main_mod, "show_stats", lambda r: self.calls.append("stats"))
        mp.setattr(main_mod, "run_round", self._run_round)
        mp.setattr(main_mod, "achievement_toast", lambda a, r: self.toasts.append(a))
        mp.setattr(main_mod, "update_stats_game", self._update_stats)
        real_create = main_mod.create_ai_players

        def create(diffs: dict[Seat, str]) -> Any:
            self.ai_diffs = dict(diffs)
            return real_create(diffs)

        mp.setattr(main_mod, "create_ai_players", create)
        mp.setattr(sys, "argv", ["belote"])

    def _update_stats(self, **kw: Any) -> list[Any]:
        self.stats_games.append(kw)
        return list(self.unlocked)

    def _run_round(self, state: GameState, *a: Any) -> GameState | None:
        self.rounds.append(state)
        res = self.round_results.pop(0)
        if isinstance(res, BaseException):
            raise res
        return res

    def run(self, *argv: str) -> None:
        sys.argv = ["belote", *argv]
        main_mod.main()


@pytest.fixture
def app(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> App:
    return App(tui, monkeypatch, ScriptedReader())


def _game_over(ns: int = 1010, ew: int = 400) -> GameState:
    return replace(new_game(), phase=Phase.GAME_OVER, team_scores=(ns, ew))


START = ("down", "down", "enter")  # BelAtro, Daily Challenge, [Start Game]


def test_main_quit_from_menu_restores_terminal(app: App) -> None:
    app.reader.push("q")
    app.run()
    assert app.calls == ["flush", "flush"]  # Quit branch + finally
    raw = app.tui.screen.raw
    from belote.ansi import alt_screen_off, alt_screen_on

    assert raw.index(alt_screen_on()) < raw.rindex(alt_screen_off())
    assert app.reader.entered == 1 and app.reader._restored


def test_main_dispatches_menu_entries(app: App) -> None:
    app.reader.push(
        *START[:2], "down", "down", "enter",  # Settings
        *START[:2], "down", "down", "down", "enter",  # Rules & History
        *START[:2], "down", "down", "down", "down", "enter",  # Statistics
        "q",
    )  # fmt: skip
    app.run()
    assert [c for c in app.calls if c != "flush"] == ["settings", "rules", "stats"]


def test_main_launches_expansion_modes(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro import integration

    launched: list[str] = []
    monkeypatch.setattr(
        integration,
        "menu_modes",
        lambda: [
            ("Mode A", lambda r: launched.append("A")),
            ("Mode B", lambda r: launched.append("B")),
        ],
    )
    app.reader.push("enter", "down", "enter", "q")
    app.run()
    assert launched == ["A", "B"]


def test_main_full_game_to_game_over_with_history_and_toasts(app: App) -> None:
    from belote.achievements import ACHIEVEMENTS

    first = ACHIEVEMENTS[0]
    app.unlocked = [first]
    mid = replace(new_game(), phase=Phase.DEAL, team_scores=(500, 300))
    app.round_results = [mid, _game_over()]
    # Start → (two rounds) → game-over screen: h (history; any key back),
    # an ignored key, Enter → menu → q.
    app.reader.push(*START, "h", "x", "space", "enter", "q")
    app.run("--seed", "7", "--target", "1000", "--difficulty", "hard", "--speed", "instant")
    assert len(app.rounds) == 2
    assert app.rounds[1] is mid
    assert app.ai_diffs == {Seat.EAST: "hard", Seat.NORTH: "hard", Seat.WEST: "hard"}
    assert app.stats_games == [{"won": True, "num_rounds": 0, "difficulty": "hard"}]
    assert app.toasts == [first]
    text = app.tui.text
    assert "GAME OVER" in text and "Winner: Team NS!" in text
    assert "GAME HISTORY" in text
    assert "[Enter/Q] Menu  [H] History" in text


def test_main_mixed_difficulty_and_ew_win(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    prefs = Settings()
    prefs.ai["north"] = "easy"
    monkeypatch.setattr(settings_mod, "load", lambda: prefs)
    app.round_results = [_game_over(ns=400, ew=1100)]
    app.reader.push(*START, "q", "q")
    app.run()
    assert app.stats_games[0]["difficulty"] == "mixed"
    assert app.stats_games[0]["won"] is False
    assert "Winner: Team EW!" in app.tui.text


def test_main_user_quits_mid_game_returns_to_menu(app: App) -> None:
    app.round_results = [None]
    app.reader.push(*START, "q")
    app.run()
    assert len(app.rounds) == 1
    assert app.stats_games == []
    assert "GAME OVER" not in app.tui.text


def test_main_keyboard_interrupt_exits_cleanly(app: App) -> None:
    from belote.ansi import alt_screen_off

    app.round_results = [KeyboardInterrupt()]
    app.reader.push(*START)
    app.run()  # must not raise
    assert alt_screen_off() in app.tui.screen.raw
    assert app.calls[-1] == "flush"


def test_main_cli_flags_override_saved_settings(app: App) -> None:
    app.reader.push("q")
    app.run("--target", "750", "--speed", "fast", "--difficulty", "easy")
    cur = settings_mod.current()
    assert cur.target == 750 and cur.speed == "fast"
    assert set(cur.ai.values()) == {"easy"}


def test_main_too_small_terminal_quit_at_startup(app: App) -> None:
    app.tui.resize(60, 20)
    app.reader.push("q")
    app.run()
    assert "Terminal too small" in app.tui.text
    assert app.rounds == []


def test_main_signal_handler_restores_and_exits(app: App) -> None:
    import signal

    from belote.ansi import alt_screen_off

    app.reader.push("q")
    app.run()
    handler = app.handlers[signal.SIGINT]
    assert app.handlers[signal.SIGTERM] is handler
    app.tui.screen.clear()
    with pytest.raises(SystemExit) as exc:
        handler(signal.SIGINT, None)
    assert exc.value.code == 0
    # guard.restore already ran in main's finally → second restore is a no-op.
    assert alt_screen_off() not in app.tui.screen.raw
    assert len(app.atexit) == 1


# ── TerminalGuard / argument parsing ────────────────────────────────────────


def test_terminal_guard_restores_reader_once_and_swallows_errors(tui: TUI) -> None:
    from belote.ansi import alt_screen_off

    class Boom(ScriptedReader):
        def restore(self) -> None:
            super().restore()
            raise OSError("tty gone")

    guard = main_mod.TerminalGuard()
    r = Boom()
    guard.enter(r.as_reader())
    guard.restore()
    assert r._restored
    assert alt_screen_off() in tui.screen.take(raw=True)
    guard.restore()
    assert tui.screen.take(raw=True) == ""


def test_terminal_guard_skips_already_restored_reader(tui: TUI) -> None:
    guard = main_mod.TerminalGuard()
    r = ScriptedReader()
    r._restored = True
    calls: list[int] = []
    r.restore = lambda: calls.append(1)  # type: ignore[method-assign]
    guard.enter(r.as_reader())
    guard.restore()
    assert calls == []


@pytest.mark.parametrize("value", ["0", "-3", "abc", "1.5"])
def test_positive_int_rejects(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        main_mod.positive_int(value)


def test_positive_int_accepts() -> None:
    assert main_mod.positive_int("750") == 750


def test_parse_args_defaults_and_errors(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["belote"])
    ns = main_mod.parse_args()
    assert (ns.target, ns.difficulty, ns.seed, ns.speed) == (None, None, None, None)
    monkeypatch.setattr(sys, "argv", ["belote", "--target", "0"])
    with pytest.raises(SystemExit):
        main_mod.parse_args()
    assert "not a positive integer" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["belote", "--version"])
    with pytest.raises(SystemExit):
        main_mod.parse_args()
    assert "belote" in capsys.readouterr().out


def test_main_menu_fits_a_default_80x24_terminal(tui: TUI) -> None:
    """4.11.0: below the cup's height the compact menu is used (the cup used
    to be clipped at the top on 24-row terminals)."""
    tui.resize(80, 24)
    assert menu.show_main_menu(tui.reader("down", "enter").as_reader(), ["BelAtro"]) == "Start Game"
    frame = tui.screen.frames()[-1] if tui.screen.frames() else tui.text
    for label in ("BelAtro", *_CORE):
        assert label in frame
    assert "B E L O T E" in frame
