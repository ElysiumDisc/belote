"""3.9.4 stats fix: the stats screen used to show only `len(unlocked_ids)`,
which is misleading because a fresh profile starts with 3 default unlocks
(le_classique, le_courageux, l_econome) while the BelAtro collection screen
filters on `discovered_items` (starts empty). Result: stats said
"3 unlocked" but the collection looked empty. Fix: show both counts.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from belote.belatro.progression.save import Profile
from belote.input import Key, KeyEvent


@dataclass
class ScriptedReader:
    events: Iterator[KeyEvent]

    def read(self) -> KeyEvent:
        return next(self.events)


def test_stats_shows_discovered_and_unlocked_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stats screen must surface both numbers so the apparent discrepancy
    with the collection screen is explainable."""
    import belote.ui.announce  # noqa: F401  — ensures the module is imported
    from belote import stats as stats_mod
    from belote.belatro.progression import save as save_mod

    announce_mod = sys.modules["belote.ui.announce"]

    # Profile with 3 unlocks (default starters) and 2 discovered items.
    profile = Profile()
    profile.discovered_items.extend(["foo", "bar"])
    monkeypatch.setattr(
        save_mod.SaveManager, "load_profile", lambda self: profile
    )

    # show_stats calls load_stats() which caches into the shared manager —
    # if other tests later monkeypatch the stats_file path, the cache hides
    # the new path. Invalidate before AND after so we don't leak state.
    stats_mod._MANAGER._stats_cache = None

    # Capture stdout.
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    # Make the loop exit on the first key press.
    reader = ScriptedReader(iter([KeyEvent(key=Key.QUIT, char=None)]))

    announce_mod.show_stats(reader)
    out = buf.getvalue()

    # Invalidate again — show_stats populated the cache.
    stats_mod._MANAGER._stats_cache = None

    assert "Discovered:" in out, "stats screen missing Discovered count"
    assert "Unlocked:" in out, "stats screen missing Unlocked count"
    assert "2 items seen" in out, f"expected '2 items seen', got: {out!r}"
    assert "3 items earned" in out, f"expected '3 items earned', got: {out!r}"
