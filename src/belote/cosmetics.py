"""Cosmetics: card backs, table frames and the milestones that unlock them.

Core-safe (no UI, no expansion imports). This module holds:

* the registries — ``CARD_BACKS`` / ``TABLE_FRAMES``, pure data that
  ``ui/cards.py`` and ``ui/table.py`` render;
* the active selection (``set_active`` / ``active_back`` / ``active_frame``),
  pushed in by ``settings.apply``; renderers key their caches on the ids;
* declarative unlock milestones (``MILESTONES``), each with a progress
  function returning ``(current, goal)``;
* the unlock-provider hook: a milestone declared with ``progress=None`` gets
  its progress function from an expansion via ``register_unlock_provider``
  (BelAtro registers ``l_insider`` / ``habitue_du_jour`` from
  ``belatro/integration.py``) — the core never imports the expansion;
* persistence of what has been earned (``<data dir>/cosmetics.json``) and
  ``check_unlocks``, which ``stats.update_stats_round/game`` call so newly
  earned items ride the existing achievement-toast path.
"""

from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from .paths import data_dir

if TYPE_CHECKING:
    from .achievements import Achievement
    from .stats import Statistics

_log = logging.getLogger(__name__)

RGB: TypeAlias = "tuple[int, int, int]"
# A colour is a fixed RGB triple, the name of a palette field of the active
# theme (``"card_back_bg"``, ``"gold_fg"`` — keeps its own fg/bg role), or
# None (no escape: terminal default).
ColorRef: TypeAlias = "tuple[int, int, int] | str | None"


# ── milestones ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Milestone:
    """An unlock condition. ``progress(stats) -> (current, goal)``; None means
    an expansion supplies it through ``register_unlock_provider``."""

    id: str
    name: str
    description: str
    progress: Callable[[Statistics], tuple[int, int]] | None = None


def _hard_wins(stats: Statistics) -> tuple[int, int]:
    hard = stats.difficulty_stats.get("hard", {})
    return hard.get("won", 0), 1


def _achievement_count(stats: Statistics) -> tuple[int, int]:
    from .achievements import ACHIEVEMENTS

    ids = {a.id for a in ACHIEVEMENTS}
    return len(ids & set(stats.achievements)), len(ids)


MILESTONES: dict[str, Milestone] = {
    m.id: m
    for m in (
        Milestone(
            "joueur_patient", "Joueur Patient", "Play 25 games.", lambda s: (s.games_played, 25)
        ),
        Milestone("le_maitre", "Le Maître", "Win a game on Hard.", _hard_wins),
        Milestone(
            "capot_collector",
            "Capot Collector",
            "Score 10 Capots.",
            lambda s: (s.capots_achieved, 10),
        ),
        Milestone("le_vainqueur", "Le Vainqueur", "Win 10 games.", lambda s: (s.games_won, 10)),
        Milestone(
            "marathonien", "Marathonien", "Play 250 rounds.", lambda s: (s.total_rounds, 250)
        ),
        Milestone("mecene", "Mécène", "Earn every Classic achievement.", _achievement_count),
        # Supplied by an expansion (BelAtro) through register_unlock_provider.
        Milestone("l_insider", "L'Insider", "Win a BelAtro run."),
        Milestone(
            "habitue_du_jour",
            "Habitué du Jour",
            "Play the Daily Challenge on 5 days.",
        ),
    )
}

_PROVIDERS: dict[str, Callable[[], tuple[int, int]]] = {}


def register_unlock_provider(milestone_id: str, progress: Callable[[], tuple[int, int]]) -> None:
    """Let an expansion supply the progress of a provider milestone (one
    declared with ``progress=None``). Re-registering replaces the function."""
    m = MILESTONES.get(milestone_id)
    if m is None or m.progress is not None:
        raise ValueError(f"{milestone_id!r} is not a provider milestone")
    _PROVIDERS[milestone_id] = progress


def unregister_unlock_provider(milestone_id: str) -> None:
    _PROVIDERS.pop(milestone_id, None)


def progress_of(m: Milestone, stats: Statistics) -> tuple[int, int] | None:
    """``(current, goal)`` with current capped at goal, or None when no
    provider is registered or the progress function failed (a broken
    expansion file must never break the core)."""
    try:
        if m.progress is not None:
            cur, goal = m.progress(stats)
        elif m.id in _PROVIDERS:
            cur, goal = _PROVIDERS[m.id]()
        else:
            return None
    except Exception as e:  # provider code reads expansion save files
        _log.info("unlock progress for %s failed: %s", m.id, e)
        return None
    cur, goal = int(cur), int(goal)
    return min(max(cur, 0), goal), goal


# ── registries ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardBack:
    """A face-down card design.

    ``pattern`` rows are tiled across the card's inner area (row ``r`` uses
    ``pattern[r % len]``), except for ``centered`` backs whose single motif
    is centred on every row (the original "Classique" back). ``small`` is
    the 2-cell chip used for opponents' hands. Every glyph is one cell wide.
    """

    id: str
    name: str
    blurb: str
    pattern: tuple[str, ...]
    pattern_ascii: tuple[str, ...]
    small: str
    small_ascii: str
    fg: ColorRef = None
    bg: ColorRef = "card_back_bg"
    milestone: str | None = None
    centered: bool = False

    @property
    def key(self) -> str:
        return f"back:{self.id}"

    @property
    def kind(self) -> str:
        return "Card back"


@dataclass(frozen=True)
class FrameGlyphs:
    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str
    ornament: str


@dataclass(frozen=True)
class TableFrame:
    """The decorative border around the trick mat (standard/spacious only).

    ``ornaments`` are fractions ``(n, d)`` of the inner width where the top and
    bottom rules carry the ornament glyph. ``glyphs_ascii`` None means no
    frame on non-UTF-8 terminals.
    """

    id: str
    name: str
    blurb: str
    glyphs: FrameGlyphs
    glyphs_ascii: FrameGlyphs | None
    ornaments: tuple[tuple[int, int], ...] = ()
    fg: str = "felt_placeholder_fg"
    bold: bool = False
    milestone: str | None = None

    @property
    def key(self) -> str:
        return f"frame:{self.id}"

    @property
    def kind(self) -> str:
        return "Table frame"


Cosmetic: TypeAlias = "CardBack | TableFrame"

DEFAULT_BACK = "classique"
DEFAULT_FRAME = "art_nouveau"

CARD_BACKS: dict[str, CardBack] = {
    b.id: b
    for b in (
        CardBack(
            "classique",
            "Classique",
            "The house lattice, in your theme's back colour.",
            ("░▒▓▒░",),
            ("XXXXX",),
            "▓▓",
            "[]",
            centered=True,
        ),
        CardBack(
            "damier",
            "Damier",
            "A café checkerboard.",
            ("▚",),
            ("#.", ".#"),
            "▚▚",
            "##",
            fg="white_fg",
        ),
        CardBack(
            "rayures",
            "Rayures",
            "Fine pinstripes.",
            ("│ ",),
            ("| ",),
            "││",
            "||",
            fg="light_gray_fg",
        ),
        CardBack(
            "tresse",
            "Tressé",
            "Woven wicker, for those who stay at the table.",
            ("⢎⡱", "⡱⢎"),
            ("/\\", "\\/"),
            "⢎⡱",
            "/\\",
            fg=(222, 196, 140),
            bg=(92, 64, 40),
            milestone="joueur_patient",
        ),
        CardBack(
            "royal",
            "Royal",
            "Gold lattice on purple velvet.",
            ("╬═", "║ "),
            ("+=", "| "),
            "╬╬",
            "%%",
            fg=(212, 175, 55),
            bg=(48, 20, 72),
            milestone="le_maitre",
        ),
        CardBack(
            "grand_chelem",
            "Grand Chelem",
            "Gold on crimson brickwork.",
            ("▄▀", "▀▄"),
            ("^v", "v^"),
            "▄▀",
            "^v",
            fg=(240, 200, 90),
            bg=(150, 30, 30),
            milestone="capot_collector",
        ),
        CardBack(
            "laurier",
            "Laurier",
            "A victor's laurel weave.",
            ("⣠⣄", "⠙⠋"),
            ("()", ")("),
            "⣠⣄",
            "@@",
            fg=(150, 200, 100),
            bg=(36, 58, 30),
            milestone="le_vainqueur",
        ),
        CardBack(
            "vague",
            "Vague",
            "A long rolling swell.",
            ("▁▂▃▄▅▆▇█▇▆▅▄▃▂",),
            ("_.-'^'-.",),
            "▃▆",
            "~~",
            fg=(120, 200, 240),
            bg=(20, 50, 90),
            milestone="marathonien",
        ),
        CardBack(
            "neon_joker",
            "Néon Joker",
            "Neon confetti from the BelAtro tables.",
            ("▖▝", "▗▘"),
            ("*.", ".*"),
            "▞▚",
            "**",
            fg=(80, 230, 200),
            bg=(30, 20, 45),
            milestone="l_insider",
        ),
        CardBack(
            "calendrier",
            "Calendrier",
            "Silver calendar foil for daily regulars.",
            ("┼──", "│  "),
            ("+--", "|  "),
            "┼┼",
            "++",
            fg=(235, 230, 215),
            bg=(70, 90, 130),
            milestone="habitue_du_jour",
        ),
    )
}

TABLE_FRAMES: dict[str, TableFrame] = {
    f.id: f
    for f in (
        TableFrame(
            "art_nouveau",
            "Art Nouveau",
            "Double rule with diamond ornaments.",
            FrameGlyphs("╔", "╗", "╚", "╝", "═", "║", "◆"),
            None,
            ornaments=((1, 3), (2, 3)),
        ),
        TableFrame(
            "minimal",
            "Minimal",
            "A single thin rule.",
            FrameGlyphs("┌", "┐", "└", "┘", "─", "│", "─"),
            FrameGlyphs("+", "+", "+", "+", "-", "|", "-"),
        ),
        TableFrame(
            "gilded",
            "Gilded",
            "Bright gold double rule with three ornaments.",
            FrameGlyphs("╔", "╗", "╚", "╝", "═", "║", "❖"),
            FrameGlyphs("*", "*", "*", "*", "=", "|", "*"),
            ornaments=((1, 4), (1, 2), (3, 4)),
            fg="gold_fg",
            bold=True,
            milestone="mecene",
        ),
    )
}


def all_items() -> Iterator[Cosmetic]:
    yield from CARD_BACKS.values()
    yield from TABLE_FRAMES.values()


def card_back(back_id: str) -> CardBack:
    return CARD_BACKS.get(back_id, CARD_BACKS[DEFAULT_BACK])


def table_frame(frame_id: str) -> TableFrame:
    return TABLE_FRAMES.get(frame_id, TABLE_FRAMES[DEFAULT_FRAME])


# ── active selection ────────────────────────────────────────────────────────

_active_back: str = DEFAULT_BACK
_active_frame: str = DEFAULT_FRAME
_callbacks: list[Callable[[], None]] = []


def register_callback(callback: Callable[[], None]) -> None:
    """Run `callback` whenever the active back or frame changes."""
    _callbacks.append(callback)


def set_active(back: str | None = None, frame: str | None = None) -> None:
    """Select the back / frame to render (unknown ids fall back to the
    defaults). Lock status is enforced by the Settings pickers, not here."""
    global _active_back, _active_frame
    new_back = _active_back if back is None else card_back(back).id
    new_frame = _active_frame if frame is None else table_frame(frame).id
    if (new_back, new_frame) == (_active_back, _active_frame):
        return
    _active_back, _active_frame = new_back, new_frame
    for cb in _callbacks:
        cb()


def active_back() -> CardBack:
    return CARD_BACKS[_active_back]


def active_frame() -> TableFrame:
    return TABLE_FRAMES[_active_frame]


# ── earned unlocks (persistence) ────────────────────────────────────────────

UNLOCKS_VERSION = 1


def unlocks_path() -> Path:
    return data_dir() / "cosmetics.json"


def load_unlocked() -> set[str]:
    """Keys (``back:<id>`` / ``frame:<id>``) of items earned so far. A
    missing, unreadable or malformed file reads as "nothing earned"."""
    try:
        raw = json.loads(unlocks_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    items = raw.get("unlocked") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return set()
    return {k for k in items if isinstance(k, str)}


def _save_unlocked(keys: set[str]) -> None:
    path = unlocks_path()
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=".cosmetics-", suffix=".tmp", delete=False
        ) as tf:
            tmp = Path(tf.name)
            json.dump({"version": UNLOCKS_VERSION, "unlocked": sorted(keys)}, tf, indent=2)
        tmp.replace(path)
    except OSError as e:
        _log.warning("Failed to save cosmetic unlocks to %s: %s", path, e)
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink()


def is_unlocked(item: Cosmetic, earned: set[str] | None = None) -> bool:
    if item.milestone is None:
        return True
    return item.key in (load_unlocked() if earned is None else earned)


def unlocked_ids(
    kind: type[CardBack] | type[TableFrame], earned: set[str] | None = None
) -> list[str]:
    """Ids of the selectable items of one kind, in registry order."""
    have = load_unlocked() if earned is None else earned
    registry: dict[str, CardBack] | dict[str, TableFrame] = (
        CARD_BACKS if kind is CardBack else TABLE_FRAMES
    )
    return [i for i, item in registry.items() if is_unlocked(item, have)]


@dataclass(frozen=True)
class Unlock:
    """An item newly earned by meeting its milestone."""

    item: Cosmetic
    milestone: Milestone

    def as_achievement(self) -> Achievement:
        """Shaped for `ui.announce.achievement_toast` (and the callers in
        gameflow / main that already toast `update_stats_*` results)."""
        from .achievements import Achievement

        return Achievement(
            f"cosmetic:{self.item.key}",
            self.item.name,
            f"{self.milestone.name}: {self.milestone.description}",
            headline=f"★ {self.item.kind.upper()} UNLOCKED ★",
        )


def check_unlocks(stats: Statistics | None = None) -> list[Unlock]:
    """Evaluate every locked item's milestone; persist and return the newly
    earned ones (each exactly once, ever). Only locked items are evaluated,
    so provider functions stop running once their item is earned."""
    if stats is None:
        from .stats import load_stats

        stats = load_stats()
    have = load_unlocked()
    new: list[Unlock] = []
    for item in all_items():
        if item.milestone is None or item.key in have:
            continue
        m = MILESTONES[item.milestone]
        prog = progress_of(m, stats)
        if prog is not None and prog[1] > 0 and prog[0] >= prog[1]:
            new.append(Unlock(item, m))
            have.add(item.key)
    if new:
        _save_unlocked(have)
    return new


def unlock_toasts(stats: Statistics | None = None) -> list[Achievement]:
    """`check_unlocks` shaped as achievements, ready for `achievement_toast`
    (for call sites outside the stats update, e.g. after a BelAtro run)."""
    return [u.as_achievement() for u in check_unlocks(stats)]
