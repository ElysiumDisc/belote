"""4.0.1 alt-screen scroll regression.

`gameflow.py` used to write `\\r\\n  X takes it as Y!\\r\\n` (and similar for
play messages and round-end results) directly to stdout. The trailing `\\n`
at the bottom of the alt-screen scrolls the entire frame up by one row on
strict terminals (Konsole observed). The render-diff layer in
`render.display()` has no idea this happened, so the next `display()` call
diffs the new frame against the cached `_last_emitted_lines` and emits zero
updates for "matching" rows — leaving the scrolled-up old frame visible
under the new one. User-visible symptom: two `Partner ▓▓▓ (N cards)` rows
stacked on top of each other after the bid→play transition.

4.0.1 fix: all such writes now route through `announce()` or
`show_round_summary()`, which paint with absolute positioning. These tests
pin the contract.
"""

from __future__ import annotations

import re
import sys

from belote.input import Key, KeyEvent
from belote.ui.announce import announce, show_round_summary


class _FakeReader:
    """Reader stub that returns ENTER immediately."""

    def read(self) -> KeyEvent:
        return KeyEvent(Key.ENTER)

    def read_timeout(self, _t: float) -> KeyEvent | None:
        return KeyEvent(Key.ENTER)


# `\r\n` in the wild — flagged as a scroll source. Inside ANSI escape
# sequences (`\x1b[...`) there is no `\n`, so a literal scan is safe.
_CRLF = re.compile(r"\r\n")


def test_announce_never_writes_crlf(capsys) -> None:
    """`announce()` must use absolute positioning, never a `\\r\\n` newline."""
    announce("Test message", duration=0)
    out = capsys.readouterr().out
    assert _CRLF.search(out) is None, f"announce() emitted \\r\\n: {out!r}"
    # Must use absolute positioning + clear_line
    assert "\x1b[" in out, "announce() should emit ANSI cursor positioning"
    assert "\x1b[K" in out or "\x1b[2K" in out, (
        "announce() should emit clear_line (^[K or ^[2K) before the banner"
    )


def test_announce_returns_keyevent_when_skipped(capsys, monkeypatch) -> None:
    """The 4.0.1 contract: announce() returns the dismiss event so callers
    can propagate skip_anims. Pre-4.0.1, announce() always returned None.
    """
    # `from belote.ui import announce` returns the *function* `announce`
    # because the ui package re-exports it. We need the module to patch
    # its `interruptible_sleep` binding — use sys.modules.
    announce_mod = sys.modules["belote.ui.announce"]

    sentinel = KeyEvent(Key.ENTER)
    monkeypatch.setattr(announce_mod, "interruptible_sleep", lambda _d, _r: sentinel)

    result = announce("Test", duration=0.5, reader=_FakeReader())  # type: ignore[arg-type]
    assert result is sentinel


def test_announce_returns_none_when_no_reader(capsys) -> None:
    """Without a reader, announce() returns None (preserves pre-4.0.1 contract
    for callers that ignored the return value)."""
    result = announce("Test", duration=0)
    assert result is None


def test_show_round_summary_no_crlf_and_invalidates_diff(capsys) -> None:
    """The round-summary modal replaces the 10-line `\\r\\n` dump that used
    to live in `gameflow.py:407-428`. It must (a) not emit any literal
    `\\r\\n` and (b) call `invalidate_diff()` so the next display() does a
    full redraw.
    """
    from dataclasses import dataclass

    from belote.deck import Suit
    from belote.game import GameState, Phase, Seat

    # `from belote.ui import render` returns the *function* `render` (the
    # ui package re-exports it), not the module. To get the module — and
    # therefore the live `_last_emitted_lines` global — use sys.modules.
    render_mod = sys.modules["belote.ui.render"]

    # Minimal ScoringBreakdown stub — only the fields show_round_summary reads
    @dataclass
    class _StubBreakdown:
        taker_team: int = 0
        taker_total: int = 100
        defender_total: int = 62
        messages: tuple[str, ...] = ("Belote announcement",)

    # Minimal GameState for the modal's `state.taker` read
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        dealer=Seat.SOUTH,
        leader=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.SCORING,
        bids=(),
        taker=Seat.SOUTH,
        current_trick=(),
        completed_tricks=(),
        last_trick_winner=None,
        team_scores=(0, 0),
        contract="normal",
    )

    render_mod._last_emitted_lines = ["sentinel"]
    skipped = show_round_summary(
        state, _StubBreakdown(), _FakeReader(), timeout=0  # type: ignore[arg-type]
    )
    out = capsys.readouterr().out

    assert _CRLF.search(out) is None, f"show_round_summary emitted \\r\\n: {out!r}"
    assert "Round Results" in re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert "Team NS" in re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert render_mod._last_emitted_lines is None, "must invalidate diff baseline"
    # The fake reader returns ENTER from both read() and read_timeout(),
    # so we get back True (user pressed something).
    assert skipped is True


def test_belatro_overlays_invalidate_diff() -> None:
    """REGRESSION: BelAtro main menu / shop / collection / rules / history
    / consumables all paint directly to stdout (clear_screen + content).
    Each render path MUST end with `invalidate_diff()`, or the BelAtro
    menu→game transition leaks the menu's ASCII-art title + option list
    onto the felt mat. User-reported via `screen-2026-05-15-22-13-41.jpg`
    overwrite (after the trick-residue surfacing).

    This is a static check — it greps the BelAtro UI source for paint
    sites and asserts each one has a nearby `invalidate_diff()` call.
    """
    import re
    from pathlib import Path

    paint_sites = {
        "src/belote/belatro/ui/menu.py": 2,
        "src/belote/belatro/ui/shop.py": 2,
        "src/belote/belatro/ui/rules.py": 1,
        "src/belote/belatro/ui/history.py": 1,
        "src/belote/belatro/ui/collection.py": 1,
        "src/belote/belatro/ui/consumables.py": 2,
        # BelAtroAnnounce.score_popup / boss_reveal / banner / yes_no /
        # slot_machine_tally (4.7.0) all paint directly with
        # `print(move(...) + ...)` and previously left their content on
        # screen "the whole time" until the next forced redraw. Each must
        # invalidate_diff() on exit.
        "src/belote/belatro/ui/announce.py": 5,
        # InventoryOverlay (4.7.0 follow-up): list view and empty-state
        # branches each end with `invalidate_diff()` in the `finally`
        # block, mirroring ConsumablesOverlay.
        "src/belote/belatro/ui/inventory.py": 1,
    }
    repo_root = Path("/home/mrrobot/belote/")
    invalidate_re = re.compile(r"invalidate_diff\s*\(\s*\)")

    for relpath, min_count in paint_sites.items():
        text = (repo_root / relpath).read_text()
        n_invalidate = len(invalidate_re.findall(text))
        assert n_invalidate >= min_count, (
            f"{relpath}: expected at least {min_count} invalidate_diff() "
            f"calls, found {n_invalidate}. Any BelAtro paint that "
            f"bypasses display() must call invalidate_diff() so the diff "
            f"baseline stays in sync."
        )


def test_patch_trick_card_invalidates_diff_baseline() -> None:
    """REGRESSION: leftover card residue between tricks.

    `patch_trick_card` writes a card directly to the terminal. If it
    doesn't invalidate the diff baseline, the next display() — typically
    at the start of the next trick — diffs the new "empty mat" frame
    against the cached "empty mat" baseline, sees no changes, and emits
    nothing. The patched cards from the previous trick stay visible. User
    reported via `screen-2026-05-15-22-13-41.jpg` (4.0.1 bug surface).
    """
    from belote.deck import Card, Rank, Suit
    from belote.game import GameState, Phase, Seat

    render_mod = sys.modules["belote.ui.render"]

    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.SPADES,
        dealer=Seat.SOUTH,
        leader=Seat.SOUTH,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        bids=(),
        taker=Seat.SOUTH,
        current_trick=(),
        completed_tricks=(),
        last_trick_winner=None,
        team_scores=(0, 0),
        contract="normal",
    )
    render_mod._last_emitted_lines = ["sentinel"]
    render_mod.patch_trick_card(state, Seat.NORTH, Card(Suit.HEARTS, Rank.KING))
    assert render_mod._last_emitted_lines is None, (
        "patch_trick_card must invalidate the diff baseline so the next "
        "display() does a full redraw — otherwise the patched card stays "
        "visible across the next trick start."
    )


def test_require_minimum_invalidates_diff_on_return(monkeypatch) -> None:
    """4.1.1 fix: `fit_guard.require_minimum` paints a centered "Terminal too
    small" overlay directly to stdout. Before 4.1.1 it returned without
    calling `invalidate_diff()`, so the diff baseline went out of sync with
    the actual terminal state — the next `display()` would diff against
    the cached pre-overlay frame and emit incomplete updates, leaving
    overlay residue visible behind the game. Same architectural rule as
    the BelAtro overlays / `patch_trick_card` / `show_round_summary`.

    We verify: small → paint overlay → resize large → return; assert
    `_last_emitted_lines` is None (the invalidation signal).
    """
    from belote.ui.fit_guard import require_minimum

    render_mod = sys.modules["belote.ui.render"]
    fit_guard_mod = sys.modules["belote.ui.fit_guard"]

    # Sentinel baseline that require_minimum must invalidate.
    render_mod._last_emitted_lines = ("sentinel-frame",)

    # First poll = small, second poll = large. The function paints once,
    # then reads (returns None to keep looping), then re-polls and exits.
    sizes = iter([(40, 20), (40, 20), (120, 40)])
    monkeypatch.setattr(fit_guard_mod, "get_term_size", lambda: next(sizes))

    class _Reader:
        def read_timeout(self, _t: float) -> KeyEvent | None:
            return None  # keep looping; next poll picks up the resize

    require_minimum(_Reader(), min_cols=80, min_rows=32)  # type: ignore[arg-type]

    assert render_mod._last_emitted_lines is None, (
        "require_minimum must call invalidate_diff() before returning when "
        "it painted the overlay — otherwise the next display() diffs "
        "against a stale baseline and leaves overlay residue on screen."
    )


def test_require_minimum_does_not_invalidate_if_never_paints(monkeypatch) -> None:
    """Fast-path: if the terminal is already large enough on the first poll,
    `require_minimum` returns immediately without painting. The diff
    baseline must NOT be touched in that case — a no-op call shouldn't
    force a full redraw on the next display().
    """
    from belote.ui.fit_guard import require_minimum

    render_mod = sys.modules["belote.ui.render"]
    fit_guard_mod = sys.modules["belote.ui.fit_guard"]

    render_mod._last_emitted_lines = ("intact-baseline",)
    monkeypatch.setattr(fit_guard_mod, "get_term_size", lambda: (200, 60))

    class _Reader:
        def read_timeout(self, _t: float) -> KeyEvent | None:
            return None

    require_minimum(_Reader(), min_cols=80, min_rows=32)  # type: ignore[arg-type]

    assert render_mod._last_emitted_lines == ("intact-baseline",), (
        "require_minimum must NOT invalidate the diff baseline when the "
        "fast path is taken (terminal already large enough — no overlay "
        "was painted)."
    )


def test_classic_ui_overlays_invalidate_diff() -> None:
    """REGRESSION (4.1.1): the classic-ui paint sites must invalidate the
    diff baseline on exit, same rule as the BelAtro overlays. Static
    check — greps the source for paint sites and asserts the
    `invalidate_diff()` count is at the expected floor.

    - `fit_guard.py::require_minimum` paints the "Terminal too small"
      overlay; pre-4.1.1 it never invalidated.
    - `announce.py::show_stats` paints the stats screen; pre-4.1.1 it
      never invalidated.
    """
    import re
    from pathlib import Path

    paint_sites = {
        # fit_guard: one invalidate_diff() inside the `finally` block.
        "src/belote/ui/fit_guard.py": 1,
        # announce.py: show_round_summary() + show_stats() each call
        # invalidate_diff(). `announce()` itself paints with absolute
        # positioning and is pinned by test_announce_never_writes_crlf to
        # never scroll, so it does NOT invalidate. Pre-4.1.1 count was 1
        # (show_round_summary only); 4.1.1 adds show_stats → 2.
        "src/belote/ui/announce.py": 2,
    }
    repo_root = Path("/home/mrrobot/belote/")
    invalidate_re = re.compile(r"invalidate_diff\s*\(\s*\)")

    for relpath, min_count in paint_sites.items():
        text = (repo_root / relpath).read_text()
        n_invalidate = len(invalidate_re.findall(text))
        assert n_invalidate >= min_count, (
            f"{relpath}: expected at least {min_count} invalidate_diff() "
            f"calls, found {n_invalidate}. Any classic-ui paint that "
            f"bypasses display() must call invalidate_diff()."
        )


def test_gameflow_no_crlf_writes() -> None:
    """No source line in `src/belote/gameflow.py` should contain a literal
    `\\r\\n` inside a `sys.stdout.write(...)` argument. This pins the
    architectural rule that broke in pre-4.0.1 and caused the two-stacks
    bug. Future writes belong in announce() / show_round_summary() /
    new dedicated modals.
    """
    import importlib.resources as _r

    src_root = _r.files("belote") / "gameflow.py"
    text = src_root.read_text()  # type: ignore[union-attr]

    # Strip docstrings (rough — we only check raw sys.stdout.write lines).
    offenders: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "sys.stdout.write" in line and "\\r\\n" in line:
            offenders.append(f"  line {lineno}: {stripped}")
    assert not offenders, (
        "gameflow.py contains scroll-inducing \\r\\n writes:\n"
        + "\n".join(offenders)
    )
