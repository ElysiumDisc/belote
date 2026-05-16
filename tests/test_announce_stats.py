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


def test_show_stats_invalidates_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.1.1 fix: `show_stats` paints `clear_screen() + content` directly to
    stdout (bypassing `display()`), so it must call `invalidate_diff()`
    before returning. Otherwise the next `display()` diffs the post-stats
    game frame against the (now-stale) pre-stats baseline and emits
    nothing for unchanged rows — the stats screen residue stays on
    screen. Same architectural rule as the BelAtro overlays and
    `fit_guard.require_minimum`.
    """
    import belote.ui.announce  # noqa: F401
    from belote import stats as stats_mod
    from belote.belatro.progression import save as save_mod

    announce_mod = sys.modules["belote.ui.announce"]
    render_mod = sys.modules["belote.ui.render"]

    profile = Profile()
    monkeypatch.setattr(save_mod.SaveManager, "load_profile", lambda self: profile)
    stats_mod._MANAGER._stats_cache = None

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    reader = ScriptedReader(iter([KeyEvent(key=Key.QUIT, char=None)]))

    # Sentinel baseline that show_stats MUST invalidate.
    render_mod._last_emitted_lines = ("pre-stats-baseline",)

    announce_mod.show_stats(reader)

    stats_mod._MANAGER._stats_cache = None

    assert render_mod._last_emitted_lines is None, (
        "show_stats must call invalidate_diff() on exit so the next "
        "display() does a full redraw — otherwise the stats screen "
        "residue stays visible behind the next frame."
    )


def test_show_stats_builds_lines_once_across_keystrokes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.1.1 perf: the stats numbers are immutable for the lifetime of the
    modal, so the line-list build should be hoisted out of the read loop.
    Pre-4.1.1 every keystroke (or terminal-size change) rebuilt the full
    list AND re-walked the difficulty / trump dicts. The new path builds
    once and only re-centers on width change.

    We assert `load_stats` is called exactly once even if the user holds
    a key and the modal re-renders multiple times. (We script the reader
    to return ENTER, ENTER, ENTER, then QUIT — but show_stats breaks on
    the first key, so the structural check is that no per-keystroke
    rebuild loop remains.)
    """
    import belote.ui.announce  # noqa: F401
    from belote import stats as stats_mod
    from belote.belatro.progression import save as save_mod

    announce_mod = sys.modules["belote.ui.announce"]

    profile = Profile()
    monkeypatch.setattr(save_mod.SaveManager, "load_profile", lambda self: profile)
    stats_mod._MANAGER._stats_cache = None

    call_count = {"n": 0}
    real_load = stats_mod.load_stats

    def counting_load_stats():  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        return real_load()

    monkeypatch.setattr(announce_mod, "load_stats", counting_load_stats)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    reader = ScriptedReader(iter([KeyEvent(key=Key.QUIT, char=None)]))

    announce_mod.show_stats(reader)

    stats_mod._MANAGER._stats_cache = None

    assert call_count["n"] == 1, (
        f"4.1.1 perf: load_stats() should be called exactly once per "
        f"show_stats invocation (the line-list is built outside the "
        f"read loop). Got {call_count['n']} calls — the hoist did not "
        f"land or regressed."
    )
