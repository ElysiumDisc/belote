"""Daily Challenge: one seeded BelAtro run per calendar day.

Everyone playing on the same date gets the same run: the seed is derived from
the date, the deck is fixed (Le Classique) and the shop draws from the
starter pool rather than the player's own unlocks, so deals, bosses and shop
rolls line up for everyone who makes the same choices. Endless mode is not
offered, so results stay comparable. Replays are allowed; the best result
per day is kept locally in ``daily.json`` next to the other data files.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from ..paths import data_dir

if TYPE_CHECKING:
    from ..input import KeyReader
    from .core.run_state import BelAtroRun
    from .progression.save import Profile

DAILY_DECK = "classique"
_EPOCH = date(2026, 1, 1)  # Daily #1
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BLIND_NAMES = ("Small", "Big", "Boss")


def daily_seed(day: date) -> int:
    """32-bit run seed for `day` (stable across platforms and versions)."""
    digest = hashlib.sha256(f"belatro-daily-{day.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


def daily_number(day: date) -> int:
    return (day - _EPOCH).days + 1


def seed_code(seed: int) -> str:
    """Short, unambiguous share code for a seed (Crockford base32, XXXX-XXX)."""
    chars = []
    for _ in range(7):
        seed, r = divmod(seed, 32)
        chars.append(_CROCKFORD[r])
    code = "".join(reversed(chars))
    return f"{code[:4]}-{code[4:]}"


@dataclass(frozen=True)
class DailyResult:
    won: bool
    ante: int
    blind: int  # 0 small, 1 big, 2 boss — the blind the run ended on
    score: int  # total chips over the run's blinds

    def sort_key(self) -> tuple[int, int, int, int]:
        return (int(self.won), self.ante, self.blind, self.score)

    def describe(self) -> str:
        if self.won:
            return f"Cleared all 8 antes · {self.score:,} chips"
        blind = _BLIND_NAMES[self.blind] if 0 <= self.blind < 3 else "?"
        return f"Ante {self.ante} · {blind} blind · {self.score:,} chips"


def result_of(run: BelAtroRun) -> DailyResult:
    return DailyResult(
        won=run.run_won,
        ante=run.ante_number,
        blind=run.blind_index,
        score=sum(entry.score for entry in run.history),
    )


def new_daily_run(day: date, profile: Profile | None = None) -> BelAtroRun:
    from .core.run_state import BelAtroRun

    return BelAtroRun(
        deck_id=DAILY_DECK, seed=daily_seed(day), profile=profile, daily=day.isoformat()
    )


# ── local best-result store ────────────────────────────────────────────────


def _store_path() -> Path:
    return data_dir() / "daily.json"


def _load_store() -> dict[str, dict[str, object]]:
    try:
        raw = json.loads(_store_path().read_text())
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def best_for(day: date) -> tuple[DailyResult | None, int]:
    """(best result, attempt count) recorded for `day`."""
    entry = _load_store().get(day.isoformat())
    if not isinstance(entry, dict):
        return None, 0
    attempts = entry.get("attempts", 0)
    best = entry.get("best")
    result: DailyResult | None = None
    if isinstance(best, dict):
        with contextlib.suppress(TypeError, ValueError):
            result = DailyResult(
                won=bool(best["won"]),
                ante=int(best["ante"]),
                blind=int(best["blind"]),
                score=int(best["score"]),
            )
    return result, attempts if isinstance(attempts, int) else 0


def record(day: date, result: DailyResult) -> bool:
    """Store an attempt; returns True when it is a new best for the day."""
    store = _load_store()
    prev, attempts = best_for(day)
    is_best = prev is None or result.sort_key() > prev.sort_key()
    store[day.isoformat()] = {
        "attempts": attempts + 1,
        "best": asdict(result if is_best or prev is None else prev),
    }
    path = _store_path()
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=".daily-", suffix=".tmp", delete=False
        ) as tf:
            tmp = Path(tf.name)
            json.dump(store, tf, indent=2, sort_keys=True)
        tmp.replace(path)
    except OSError:
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink()
    return is_best


# ── screens ────────────────────────────────────────────────────────────────


def intro_lines(day: date) -> list[str]:
    """Pure line-builder for the Daily Challenge intro screen."""
    from ..ansi import BOLD, DIM, RESET, gold_fg, white_fg

    best, attempts = best_for(day)
    played = (
        f"Today's best: {best.describe()}  ({attempts} attempt{'s' if attempts != 1 else ''})"
        if best is not None
        else "Not played yet today."
    )
    return [
        f"{BOLD}{gold_fg()}DAILY CHALLENGE #{daily_number(day)}{RESET}",
        f"{white_fg()}{day.strftime('%A %d %B %Y')}{RESET}",
        "",
        f"Seed code: {BOLD}{seed_code(daily_seed(day))}{RESET}    Deck: Le Classique",
        "",
        "Everyone gets the same deals, bosses and shop pool today —",
        "compare how far you get with friends.",
        "",
        played,
        "",
        f"{DIM}[Enter] Play   [Esc] Back{RESET}",
    ]


def _show(lines: list[str], reader: KeyReader) -> bool:
    """Paint centered `lines`; True if the player pressed Enter."""
    from ..ansi import ansi_center, clear_screen, hide_cursor
    from ..input import Key
    from ..ui.layout import vcenter_lines
    from ..ui.render import get_term_size, invalidate_diff

    term_w, term_h = get_term_size()
    body = vcenter_lines([ansi_center(line, term_w) for line in lines], term_h)
    sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(body))
    sys.stdout.flush()
    invalidate_diff()
    while True:
        key = reader.read().key
        if key == Key.ENTER:
            return True
        if key in (Key.ESC, Key.QUIT, Key.EOF, Key.SPACE):
            return False


def play_daily(reader: KeyReader, day: date | None = None) -> None:
    """Main-menu launcher: intro → run → result."""
    from ..ansi import BOLD, RESET, gold_fg, green_fg
    from .main import BelAtroGame, toast_cosmetic_unlocks

    day = day or date.today()
    if not _show(intro_lines(day), reader):
        return
    game = BelAtroGame()
    game.start(reader, run=new_daily_run(day, game.profile))
    run = game.run
    if run is None or not run.history:
        return  # quit before finishing a blind: nothing to record
    result = result_of(run)
    new_best = record(day, result)
    tag = f"{green_fg()}{BOLD}NEW BEST!{RESET}" if new_best else ""
    _show(
        [
            f"{BOLD}{gold_fg()}DAILY CHALLENGE #{daily_number(day)} — RESULT{RESET}",
            "",
            result.describe(),
            tag,
            "",
            f"Share: Daily #{daily_number(day)} ({seed_code(daily_seed(day))}) — {result.describe()}",
            "",
            "[Enter] Back",
        ],
        reader,
    )
    # daily.json was just written: the calendar card back may now be earned.
    toast_cosmetic_unlocks(reader)
