"""Wire BelAtro into the core game's extension points.

The core never imports BelAtro. The app entry point (`belote.main`) and the
standalone `belatro` command call `install()` once; it registers the pieces
of the core UI that BelAtro contributes to. Imports stay lazy so classic play
doesn't load the expansion until it is used.

It also supplies the progress of the BelAtro-earned cosmetic unlocks (the
"Néon Joker" and "Calendrier" card backs) through
`cosmetics.register_unlock_provider`.

Run-scoped hooks (history override, bid hint, extension keys) are installed
by `BelAtroGame.start` for the duration of a run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..settings import Toggle

if TYPE_CHECKING:
    from ..input import KeyReader

# Settings-screen toggle for ghost-run recording. BELOTE_GHOST still forces it on.
GHOST_TOGGLE = Toggle("belatro_ghost_recording", "Ghost run recording", False, "BELOTE_GHOST")

_installed = False


def stats_lines() -> list[str]:
    """BelAtro's section of the global Statistics screen."""
    from ..ansi import BOLD, RESET, gold_fg
    from .progression.save import SaveManager

    profile = SaveManager().load_profile()
    b_stats = profile.stats
    return [
        f"{BOLD}{gold_fg()}BELATRO EXPANSION{RESET}",
        "-" * 17,
        f"  Runs Won (Ante 8): {b_stats.get('runs_won', 0)}",
        f"  Total Capots:      {b_stats.get('total_capots', 0)}",
        f"  Boss Blinds Won:   {b_stats.get('bosses_defeated', 0)}",
        f"  Special Wins:      Sans Atout: {b_stats.get('sans_atout_wins', 0)}  "
        f"Tout Atout: {b_stats.get('tout_atout_wins', 0)}",
        f"  Discovered:        {len(profile.discovered_items)} items seen",
        f"  Unlocked:          {len(profile.unlocked_ids)} items earned",
        "",
    ]


def insider_progress() -> tuple[int, int]:
    """Cosmetic milestone "L'Insider": win a BelAtro run."""
    from .progression.save import SaveManager

    won = SaveManager().load_profile().stats.get("runs_won", 0)
    return (won if isinstance(won, int) else 0), 1


DAILY_DAYS_GOAL = 5


def daily_days_progress() -> tuple[int, int]:
    """Cosmetic milestone "Habitué du Jour": Daily Challenge played on
    `DAILY_DAYS_GOAL` different days (days with an attempt in daily.json)."""
    from .daily import _load_store

    days = 0
    for entry in _load_store().values():
        attempts = entry.get("attempts") if isinstance(entry, dict) else None
        if isinstance(attempts, int) and attempts > 0:
            days += 1
    return days, DAILY_DAYS_GOAL


def _launch_belatro(reader: KeyReader) -> None:
    from .main import BelAtroGame

    BelAtroGame().start(reader)


def _launch_daily(reader: KeyReader) -> None:
    from .daily import play_daily

    play_daily(reader)


def menu_modes() -> list[tuple[str, Callable[[KeyReader], None]]]:
    """Game modes BelAtro adds to the core main menu, in display order."""
    return [("BelAtro", _launch_belatro), ("Daily Challenge", _launch_daily)]


def install() -> None:
    """Register BelAtro's app-level contributions to the core UI (idempotent)."""
    global _installed
    if _installed:
        return
    from ..cosmetics import register_unlock_provider
    from ..settings import register_toggle
    from ..ui.announce import register_stats_section

    register_stats_section(stats_lines)
    register_toggle(GHOST_TOGGLE)
    # Progress of the core cosmetics that BelAtro play unlocks.
    register_unlock_provider("l_insider", insider_progress)
    register_unlock_provider("habitue_du_jour", daily_days_progress)
    _installed = True
