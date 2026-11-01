"""Wire BelAtro into the core game's extension points.

The core never imports BelAtro. The app entry point (`belote.main`) and the
standalone `belatro` command call `install()` once; it registers the pieces
of the core UI that BelAtro contributes to. Imports stay lazy so classic play
doesn't load the expansion until it is used.

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
        f"  Special Wins:      Sans Atout: {b_stats.get('sans_atout_wins', 0)}  "
        f"Tout Atout: {b_stats.get('tout_atout_wins', 0)}",
        f"  Discovered:        {len(profile.discovered_items)} items seen",
        f"  Unlocked:          {len(profile.unlocked_ids)} items earned",
        "",
    ]


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
    from ..settings import register_toggle
    from ..ui.announce import register_stats_section

    register_stats_section(stats_lines)
    register_toggle(GHOST_TOGGLE)
    _installed = True
