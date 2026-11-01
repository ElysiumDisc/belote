"""Spectate mode screens: the "who takes this round?" prediction and the
persistent best prediction streak (`spectate.json` in the data dir)."""

from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass

from ..ansi import BOLD, RESET, ansi_center, clear_screen, gold_fg, hide_cursor, light_gray_fg
from ..game import GameState
from ..input import Key, KeyReader
from ..paths import data_dir
from .render import get_term_size, invalidate_diff

_FILE = "spectate.json"


@dataclass
class Streak:
    current: int = 0
    best: int = 0
    correct: int = 0
    guesses: int = 0

    def record(self, guess: int | None, winner: int | None) -> bool | None:
        """Score one prediction (team 0 = NS, 1 = EW). None = no guess or no
        winner (all passed / a tie): nothing changes."""
        if guess is None or winner is None:
            return None
        self.guesses += 1
        if guess == winner:
            self.correct += 1
            self.current += 1
            self.best = max(self.best, self.current)
            return True
        self.current = 0
        return False


def load_best() -> int:
    try:
        data = json.loads((data_dir() / _FILE).read_text(encoding="utf-8"))
        best = data.get("best_streak", 0)
        return best if isinstance(best, int) and best >= 0 else 0
    except (OSError, ValueError, AttributeError):
        return 0


def save_best(best: int) -> None:
    with contextlib.suppress(OSError):
        path = data_dir() / _FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"best_streak": best}), encoding="utf-8")


def round_winner(before: GameState, after: GameState) -> int | None:
    """The team that banked more points this round (None on a tie / redeal)."""
    d_ns = after.team_scores[0] - before.team_scores[0]
    d_ew = after.team_scores[1] - before.team_scores[1]
    if d_ns == d_ew:
        return None
    return 0 if d_ns > d_ew else 1


def ask_prediction(reader: KeyReader, round_no: int, streak: Streak, pace_label: str) -> int | str:
    """Return 0 (NS), 1 (EW), -1 (no guess) or "QUIT"."""
    term_w, term_h = get_term_size()
    lines = [
        f"{BOLD}{gold_fg()}Spectate — round {round_no}{RESET}",
        "",
        "Who takes this round?",
        "",
        f"{BOLD}[←] North-South        East-West [→]{RESET}",
        f"{light_gray_fg()}Enter: just watch{RESET}",
        "",
        f"Streak {streak.current}   Best {streak.best}   ({streak.correct}/{streak.guesses} right)",
        "",
        f"{light_gray_fg()}While watching:  + / - speed ({pace_label})   "
        f"Space pause   Q stop{RESET}",
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
        if ev.key in (Key.LEFT, Key.UP):
            return 0
        if ev.key in (Key.RIGHT, Key.DOWN):
            return 1
        if ev.key in (Key.ENTER, Key.SPACE):
            return -1
        if ev.key in (Key.QUIT, Key.ESC, Key.EOF):
            return "QUIT"
