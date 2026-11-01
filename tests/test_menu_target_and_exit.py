"""Main menu / game-over / main-loop regressions.

- `--target 750` (any positive int is accepted) crashed the menu's target row
  with ValueError from `targs.index`; it now snaps to the nearest preset.
- The game-over screen wrote bare "\\n" under raw mode (OPOST off), so each
  line started where the previous one ended (staircase).
- `FitAbortedError` from an in-game resize prompt escaped `main()` as a
  traceback; only the startup `require_minimum` call caught it.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from typing import Any

import pytest

from belote.game import Seat, new_game
from belote.input import Key, KeyEvent
from belote.ui.menu import _step_target, show_final_screen, show_main_menu

_TARGS = [500, 1000, 1500, 2000]


@pytest.mark.parametrize(
    ("curr", "delta", "expected"),
    [
        (1000, 1, 1500),
        (2000, 1, 500),
        (500, -1, 2000),
        (750, 1, 1000),
        (750, -1, 500),
        (5000, 1, 500),
        (5000, -1, 2000),
        (100, -1, 2000),
        (100, 1, 500),
    ],
)
def test_step_target(curr: int, delta: int, expected: int) -> None:
    assert _step_target(_TARGS, curr, delta) == expected


class _ScriptedReader:
    def __init__(self, events: list[KeyEvent]) -> None:
        self._events = list(events)

    def read(self) -> KeyEvent:
        return self._events.pop(0)

    def read_timeout(self, _t: float) -> KeyEvent | None:
        return self._events.pop(0)


@pytest.mark.parametrize(("key", "expected"), [(Key.RIGHT, 1000), (Key.LEFT, 500), (Key.ENTER, 1000)])
def test_main_menu_non_preset_target_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, key: Key, expected: int
) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    events = [KeyEvent(Key.DOWN)] * 3 + [KeyEvent(key), KeyEvent(Key.QUIT)]
    diffs = {Seat.EAST: "medium", Seat.NORTH: "medium", Seat.WEST: "medium"}
    choice, _, target, _ = show_main_menu(
        _ScriptedReader(events),  # type: ignore[arg-type]
        diffs,
        750,
        "normal",
    )
    assert choice == "Quit"
    assert target == expected


def test_final_screen_uses_crlf(monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    show_final_screen(new_game())
    out = buf.getvalue()
    assert "\r\n" in out
    assert re.search(r"(?<!\r)\n", out) is None, "bare LF staircases under raw mode"


class _FakeKeyReader:
    _restored = False

    def __enter__(self) -> _FakeKeyReader:
        return self

    def __exit__(self, *_a: Any) -> None:
        self._restored = True

    def restore(self) -> None:
        self._restored = True

    def read(self) -> KeyEvent:
        return KeyEvent(Key.QUIT)


def test_main_exits_cleanly_on_in_game_fit_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    import atexit
    import signal

    import belote.main as main_mod
    import belote.ui.fit_guard as fit_guard
    from belote.ui.fit_guard import FitAbortedError

    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(signal, "signal", lambda *_a: None)
    monkeypatch.setattr(atexit, "register", lambda *_a: None)
    monkeypatch.setattr(
        main_mod,
        "parse_args",
        lambda: argparse.Namespace(target=1000, difficulty="medium", seed=1, speed="instant"),
    )
    monkeypatch.setattr(main_mod, "KeyReader", _FakeKeyReader)
    monkeypatch.setattr(main_mod, "flush_stats", lambda: None)
    monkeypatch.setattr(fit_guard, "require_minimum", lambda *_a, **_k: None)
    monkeypatch.setattr(
        main_mod,
        "show_main_menu",
        lambda _r, diffs, target, speed: ("Start Game", diffs, target, speed),
    )

    def raise_fit(*_a: Any, **_k: Any) -> None:
        raise FitAbortedError

    monkeypatch.setattr(main_mod, "run_round", raise_fit)

    main_mod.main()  # must return, not raise

    from belote.ansi import alt_screen_off

    # TerminalGuard.restore ran (alt screen left) via main's finally block.
    assert alt_screen_off() in sys.stdout.getvalue()  # type: ignore[attr-defined]
