"""4.11.0 — Boss Rush / Challenge Seed setup screen.

Starts a normal BelAtro run with a chosen starting ante (1–8), a pinned boss
(or random), any *unlocked* starting deck, an optional seed, and optionally
every blind turned into a boss blind. The run then plays through the regular
run loop; it is flagged `challenge` so it doesn't count toward run-level
milestones (runs won, ante unlocks, Boss Blind tally).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    white_fg,
)
from belote.input import Key

if TYPE_CHECKING:
    from belote.input import KeyEvent, KeyReader

    from ..core.run_state import BelAtroRun
    from ..progression.save import Profile
    from ..run.decks import StartingDeck

ROWS: tuple[str, ...] = ("Start Ante", "Boss", "Deck", "Seed", "Every blind a boss", "Start")
_ROW_SEED = ROWS.index("Seed")
_ROW_START = ROWS.index("Start")
_MAX_SEED_DIGITS = 10
_BACKSPACE = ("\x7f", "\x08")


@dataclass
class BossRushSetup:
    """The screen's editable choices (pure state, easy to test)."""

    decks: list[StartingDeck]
    boss_ids: list[str | None] = field(default_factory=list)  # None = random
    row: int = 0
    ante: int = 1
    boss_idx: int = 0
    deck_idx: int = 0
    seed_text: str = ""
    every_blind_boss: bool = True

    @property
    def boss_id(self) -> str | None:
        return self.boss_ids[self.boss_idx] if self.boss_ids else None

    @property
    def deck(self) -> StartingDeck:
        return self.decks[self.deck_idx]

    @property
    def seed(self) -> int | None:
        return int(self.seed_text) if self.seed_text else None

    def step(self, delta: int) -> None:
        """LEFT / RIGHT on the current row."""
        if self.row == 0:
            self.ante = (self.ante - 1 + delta) % 8 + 1
        elif self.row == 1 and self.boss_ids:
            self.boss_idx = (self.boss_idx + delta) % len(self.boss_ids)
        elif self.row == 2:
            self.deck_idx = (self.deck_idx + delta) % len(self.decks)
        elif self.row == _ROW_SEED and delta < 0:
            self.seed_text = self.seed_text[:-1]
        elif self.row == 4:
            self.every_blind_boss = not self.every_blind_boss

    def type_char(self, ch: str) -> None:
        if self.row != _ROW_SEED:
            return
        if ch in _BACKSPACE:
            self.seed_text = self.seed_text[:-1]
        elif ch.isdigit() and len(self.seed_text) < _MAX_SEED_DIGITS:
            self.seed_text = (self.seed_text + ch).lstrip("0") or "0"

    def build_run(self, profile: Profile) -> BelAtroRun:
        from ..core.run_state import BelAtroRun

        return BelAtroRun(
            deck_id=self.deck.id,
            profile=profile,
            seed=self.seed,
            ante_number=self.ante,
            challenge=True,
            boss_rush=self.every_blind_boss,
            challenge_boss_id=self.boss_id,
        )


def new_setup(profile: Profile) -> BossRushSetup:
    from ..run.boss import ALL_BOSS_MODIFIERS
    from ..run.decks import unlocked_decks

    return BossRushSetup(
        decks=unlocked_decks(profile),
        boss_ids=[None, *(cls.id for cls in ALL_BOSS_MODIFIERS)],
    )


def _value_label(setup: BossRushSetup, row: int) -> str:
    from ..run.boss import BOSS_BY_ID

    if row == 0:
        return f"◀ {setup.ante} ▶"
    if row == 1:
        boss = BOSS_BY_ID.get(setup.boss_id or "")
        return f"◀ {boss.name if boss is not None else 'Random'} ▶"
    if row == 2:
        return f"◀ {setup.deck.name} ▶"
    if row == _ROW_SEED:
        return (setup.seed_text or "random") + ("_" if setup.row == _ROW_SEED else "")
    if row == 4:
        return f"◀ {'Yes' if setup.every_blind_boss else 'No'} ▶"
    return ""


def boss_rush_lines(setup: BossRushSetup, term_w: int) -> list[str]:
    """Pure line builder for the setup screen (≈17 rows)."""
    from belote.ui.text import wrap_words

    from ..run.boss import BOSS_BY_ID

    lines = [
        ansi_center(gold_fg() + BOLD + "BOSS RUSH / CHALLENGE SEED" + RESET, term_w),
        ansi_center(DIM + "Practice runs don't count toward unlock milestones." + RESET, term_w),
        "",
    ]
    for i, label in enumerate(ROWS):
        text = "[ Start ]" if i == _ROW_START else f"{label:<20} {_value_label(setup, i):<26}"
        color = REVERSE + gold_fg() + BOLD if i == setup.row else white_fg()
        lines.append(ansi_center(color + text + RESET, term_w))
    lines.append("")
    boss = BOSS_BY_ID.get(setup.boss_id or "")
    blurb = (
        f"{boss.name}: {boss.description}"
        if boss is not None
        else "Boss: a random boss each boss blind."
    )
    blurb += f"  Deck: {setup.deck.description}"
    for line in wrap_words(blurb, max(30, min(term_w - 8, 72)))[:4]:
        lines.append(ansi_center(white_fg() + line + RESET, term_w))
    lines.append("")
    lines.append(
        ansi_center(
            light_gray_fg() + "↑↓ Row  ←→ Change  0-9 Seed  Enter: Start  Esc: Back" + RESET,
            term_w,
        )
    )
    return lines


def handle_key(setup: BossRushSetup, event: KeyEvent) -> str | None:
    """Apply one key. Returns "start", "back" or None (keep editing)."""
    key = event.key
    if key in (Key.ESC, Key.QUIT, Key.EOF):
        return "back"
    if key == Key.ENTER:
        return "start"
    if setup.row == _ROW_SEED and event.char is not None and event.char.isdigit():
        setup.type_char(event.char)
    elif key == Key.UP:
        setup.row = (setup.row - 1) % len(ROWS)
    elif key == Key.DOWN:
        setup.row = (setup.row + 1) % len(ROWS)
    elif key == Key.LEFT:
        setup.step(-1)
    elif key == Key.RIGHT:
        setup.step(+1)
    elif key == Key.CHAR and event.char:
        setup.type_char(event.char)
    return None


_ARROW_ROWS = (0, 1, 2, 4)  # rows whose value steps with ◀ ▶


def click_targets() -> list[tuple[str, object]]:
    """5.0.0 mouse: each row's label selects it, its ◀ / ▶ step it, and
    "[ Start ]" starts — in screen order, for `hitmap.targets_from_lines`."""
    targets: list[tuple[str, object]] = []
    for i, label in enumerate(ROWS):
        if i == _ROW_START:
            targets.append(("[ Start ]", ("start", i)))
            continue
        targets.append((label, ("row", i)))
        if i in _ARROW_ROWS:
            targets += [("◀", ("step", i, -1)), ("▶", ("step", i, +1))]
    return targets


def handle_click(setup: BossRushSetup, target: object) -> str | None:
    """Apply a click target. Returns "start" or None, like `handle_key`."""
    if not isinstance(target, tuple):
        return None
    if target[0] == "start":
        return "start"
    setup.row = int(target[1])
    if target[0] == "step":
        setup.step(int(target[2]))
    return None


def show_boss_rush(reader: KeyReader, profile: Profile) -> BelAtroRun | None:
    """Run the setup screen; the configured run, or None on Esc."""
    from belote.ui.fit_guard import require_minimum
    from belote.ui.layout import vcenter_lines
    from belote.ui.render import get_term_size, invalidate_diff

    setup = new_setup(profile)
    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()
        body = vcenter_lines(boss_rush_lines(setup, term_w), term_h)
        sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(body))
        sys.stdout.flush()
        invalidate_diff()
        from belote.ui import hitmap

        hitmap.targets_from_lines("menu", body, click_targets(), pad=1)
        event = reader.read()
        if event.key == Key.MOUSE:
            action = handle_click(setup, hitmap.hit("menu", event.pos))
        else:
            action = handle_key(setup, event)
        if action == "back":
            return None
        if action == "start":
            return setup.build_run(profile)
