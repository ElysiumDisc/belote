"""Who sits at the classic table: the solo game, Spectate, Hot-seat.

`TableMode` tells the classic round policy (`gameflow.ClassicRound`) which
seats are human and how to present the table:

* `SOLO` — the classic game: SOUTH is the human, everyone else is AI.
* `spectate()` — four AIs; a `PaceControl` lets the watcher speed up / slow
  down / pause, and quit, through a `SpectatorReader` wrapping the keyboard.
* `hotseat(seats)` — 2–4 humans share one terminal. The table is always drawn
  from the chair of whoever holds the device (`game.rotate_view`), and a
  blank "pass the device" screen hides the hands whenever it changes hands.
  Undo is off (it would replay another player's hidden decision).

Classic code paths only look at `mode.humans` / `mode.hotseat` /
`mode.pace`, so the solo game behaves exactly as before (verified by
`scripts/fingerprint.py`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from .ansi import BOLD, RESET, ansi_center, clear_screen, gold_fg, hide_cursor, light_gray_fg
from .context import TERMINAL
from .game import Seat
from .input import Key, KeyEvent, KeyReader, typed

# Spectator speed steps: multipliers on the configured AI delay / trick pause.
_PACE_STEPS: tuple[float, ...] = (2.0, 1.5, 1.0, 0.6, 0.35, 0.15, 0.0)
_DEFAULT_PACE = 2


@dataclass
class PaceControl:
    """Spectator playback state, shared by the reader wrapper and the policy."""

    step: int = _DEFAULT_PACE
    quit: bool = False

    @property
    def scale(self) -> float:
        return _PACE_STEPS[self.step]

    @property
    def label(self) -> str:
        return "max" if self.scale == 0 else f"×{1 / self.scale:.1f}"

    def faster(self) -> None:
        self.step = min(len(_PACE_STEPS) - 1, self.step + 1)

    def slower(self) -> None:
        self.step = max(0, self.step - 1)


@dataclass(frozen=True)
class TableMode:
    humans: frozenset[Seat] = frozenset({Seat.SOUTH})
    hotseat: bool = False
    pace: PaceControl | None = field(default=None, compare=False)

    @property
    def is_solo(self) -> bool:
        return self.humans == frozenset({Seat.SOUTH}) and not self.hotseat

    @property
    def records_stats(self) -> bool:
        """Only the solo game feeds the player's statistics/achievements."""
        return self.is_solo


SOLO = TableMode()


def spectate() -> TableMode:
    return TableMode(humans=frozenset(), pace=PaceControl())


def hotseat(seats: frozenset[Seat]) -> TableMode:
    if not 2 <= len(seats) <= 4:
        raise ValueError("hot-seat needs 2 to 4 human seats")
    return TableMode(humans=seats, hotseat=True)


# Presets offered by the hot-seat setup menu.
HOTSEAT_PRESETS: tuple[tuple[str, frozenset[Seat]], ...] = (
    ("2 players — partners (South + North)", frozenset({Seat.SOUTH, Seat.NORTH})),
    ("2 players — opponents (South + East)", frozenset({Seat.SOUTH, Seat.EAST})),
    ("3 players (South, East, North)", frozenset({Seat.SOUTH, Seat.EAST, Seat.NORTH})),
    ("4 players", frozenset(Seat)),
)

# A key the spectator wrapper consumed (speed / pause): the policy must not
# treat it as "skip the animations".
_CONSUMED = KeyEvent(Key.UNKNOWN, "\x00spectate")


def consumed(event: object) -> bool:
    return event is _CONSUMED


class SpectatorReader(KeyReader):
    """Keyboard wrapper for Spectate: `+`/`-` change speed, Space pauses,
    Q / Esc stop watching. Other keys pass through (they skip the current
    animation, as in the solo game)."""

    def __init__(self, inner: KeyReader, pace: PaceControl) -> None:
        self._inner = inner
        self.pace = pace

    def __enter__(self) -> SpectatorReader:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def restore(self) -> None:
        self._inner.restore()

    def read(self) -> KeyEvent:
        return self._filter(self._inner.read())

    def read_timeout(self, timeout: float) -> KeyEvent | None:
        ev = self._inner.read_timeout(timeout)
        return None if ev is None else self._filter(ev)

    def _filter(self, ev: KeyEvent) -> KeyEvent:
        if typed(ev, "+") or typed(ev, "="):
            self.pace.faster()
            return _CONSUMED
        if typed(ev, "-") or typed(ev, "_"):
            self.pace.slower()
            return _CONSUMED
        if ev.key == Key.SPACE:
            self._pause()
            return _CONSUMED
        if ev.key in (Key.QUIT, Key.ESC, Key.EOF):
            self.pace.quit = True
        return ev

    def _pause(self) -> None:
        _bottom_line(f"{BOLD}{gold_fg()}⏸ Paused{RESET}  {light_gray_fg()}Space: resume{RESET}")
        while True:
            ev = self._inner.read()
            if ev.key in (Key.SPACE, Key.ENTER):
                return
            if ev.key in (Key.QUIT, Key.ESC, Key.EOF):
                self.pace.quit = True
                return


def _bottom_line(text: str) -> None:
    term_w, term_h = TERMINAL.get_size()
    sys.stdout.write(f"\x1b[{term_h};1H\x1b[2K{ansi_center(text, term_w)}")
    sys.stdout.flush()


def pass_device_screen(reader: KeyReader, seat: Seat, players: int) -> bool:
    """Blank the table and ask the next player to take the device.

    Returns False if they chose to quit (Q / EOF)."""
    from .ui.render import invalidate_diff

    term_w, term_h = TERMINAL.get_size()
    lines = [
        f"{BOLD}{gold_fg()}Pass the device{RESET}",
        "",
        f"{BOLD}{seat.name}{RESET}'s turn  ({players} players at the table)",
        "",
        f"{light_gray_fg()}Everyone else: look away.  Enter: show my hand   Q: quit{RESET}",
    ]
    top = max(1, (term_h - len(lines)) // 2)
    out = [clear_screen(), hide_cursor()]
    for i, line in enumerate(lines):
        out.append(f"\x1b[{top + i};1H{ansi_center(line, term_w)}")
    sys.stdout.write("".join(out))
    sys.stdout.flush()
    invalidate_diff()
    while True:
        ev = reader.read()
        if ev.key in (Key.ENTER, Key.SPACE):
            return True
        if ev.key in (Key.QUIT, Key.EOF):
            return False
