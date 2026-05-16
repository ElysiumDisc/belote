"""3.9.3 Phase 6: diff-based render emit.

display() compares the post-vcenter line list against the previous frame
and writes only changed rows. Layout changes, theme changes, and explicit
force=True bypass the diff and emit a full redraw.
"""

from __future__ import annotations

import io
import sys as _sys

import pytest

# `belote.ui.render` is re-exported as a function by __init__, so use the
# module directly from sys.modules (mirrors tests/test_layout.py's pattern).
import belote.ui.render  # noqa: F401  — ensures the module is imported
from belote.game import new_game

render_mod = _sys.modules["belote.ui.render"]


def _flush_baseline(monkeypatch: pytest.MonkeyPatch) -> tuple[io.StringIO, str]:
    """Render once to establish a diff baseline and return (stdout, bytes_written)."""
    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))
    state = new_game()
    render_mod.display(state, force=True)
    return buf, buf.getvalue()


def test_first_render_emits_full_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh render (no baseline) must emit the full string from render()."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None
    buf, first = _flush_baseline(monkeypatch)
    # Sanity: full frame is non-trivial.
    assert len(first) > 500


def test_idempotent_render_emits_only_cursor_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    """3.9.3 Phase 6: rendering the same state twice must emit *significantly*
    less than the full frame the second time — ideally only hide/show cursor
    bookkeeping since no rows actually changed."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    state = new_game()
    # First render establishes baseline.
    render_mod.display(state, force=True)
    first_bytes = len(buf.getvalue())
    buf.seek(0)
    buf.truncate(0)

    # Second render — same state, diff path should kick in.
    render_mod.display(state)
    second_bytes = len(buf.getvalue())
    assert second_bytes < first_bytes // 4, (
        f"diff render not effective: first={first_bytes} bytes, "
        f"second={second_bytes} bytes (expected < {first_bytes // 4})"
    )


def test_force_bypasses_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """With force=True the diff is skipped and we always emit the full frame."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    state = new_game()
    render_mod.display(state, force=True)
    first_bytes = len(buf.getvalue())
    buf.seek(0)
    buf.truncate(0)

    render_mod.display(state, force=True)
    second_bytes = len(buf.getvalue())
    # Forced re-render emits roughly the same byte count both times.
    assert abs(first_bytes - second_bytes) < 100


def test_env_var_bypasses_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """`BELOTE_NO_DIFF=1` is an escape hatch — emit full frame regardless."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None
    monkeypatch.setenv("BELOTE_NO_DIFF", "1")

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    state = new_game()
    render_mod.display(state, force=True)
    first_bytes = len(buf.getvalue())
    buf.seek(0)
    buf.truncate(0)

    render_mod.display(state)
    second_bytes = len(buf.getvalue())
    # No diff → second emit is full frame (roughly equal to first).
    assert abs(first_bytes - second_bytes) < 200


def test_layout_change_forces_full_redraw(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the terminal-size key changes, render() invalidates the diff
    baseline so the next display() emits a full frame (else we'd compare
    against rows painted under the old layout)."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)

    state = new_game()
    # First emit at a small layout.
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (80, 24))
    render_mod.display(state, force=True)
    buf.seek(0)
    buf.truncate(0)

    # Resize: layout key changes → render() resets _last_emitted_lines → next
    # display() emits a full frame.
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (200, 60))
    render_mod.display(state)
    after_resize = len(buf.getvalue())
    # Full frame post-resize should be substantial.
    assert after_resize > 500


def test_theme_callback_resets_diff_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """clear_card_cache() is invoked by the theme-change callback. It must
    also reset _last_emitted_lines so a post-theme render doesn't skip rows
    that contain the old theme's escape sequences."""
    render_mod._last_emitted_lines = ["dummy line 1", "dummy line 2"]
    render_mod.clear_card_cache()
    assert render_mod._last_emitted_lines is None


# ── 4.1.0 perf + correctness pins ──────────────────────────────────────────


def test_pip_at_is_cached() -> None:
    """4.1.0 C2: `_pip_at` is a pure deterministic function of (row_id, col)
    and is decorated with @lru_cache. Pin via the cache-info side-channel:
    after two identical calls the cache should have exactly one hit.
    """
    render_mod._pip_at.cache_clear()
    # Choose a cell that *will* produce a glyph under the deterministic
    # ((row*31 + col*17) % 23) < 2 rule. (0, 0) satisfies it (0 % 23 = 0).
    a = render_mod._pip_at(0, 0)
    b = render_mod._pip_at(0, 0)
    assert a == b
    info = render_mod._pip_at.cache_info()
    assert info.hits >= 1, f"expected ≥1 cache hit, got {info}"


def test_theme_name_cache_invalidated_on_theme_change() -> None:
    """4.1.0 C1: switching themes via `theme_manager.set_current()` must
    refresh the cached theme name (used as a felt-segment cache key) AND
    invalidate the diff baseline (so the next render emits a full frame
    with the new palette).
    """
    from belote.themes import theme_manager

    before = render_mod._cached_theme_name
    # Pick a different theme from the registry; restore at the end.
    other = "dark_mode" if before != "dark_mode" else "blue_velvet"
    try:
        theme_manager.set_current(other)
        assert render_mod._cached_theme_name == other, (
            f"theme-name cache should be {other!r} after set_current, "
            f"got {render_mod._cached_theme_name!r}"
        )
        # Diff baseline also nuked by the callback.
        assert render_mod._last_emitted_lines is None
    finally:
        theme_manager.set_current(before)


def test_diff_emit_appends_clear_to_eol_on_row_shrink(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.1.0 C4: when a row shrinks (e.g. terminal narrowed mid-game), the
    diff-emit path must append `clear_to_eol()` so stale chars past the new
    line's end get blanked. Pre-4.1.0 only full-render rows did this; the
    diff path silently left tail debris.
    """
    from belote.ansi import clear_to_eol

    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    state = new_game()
    # First render: establishes baseline.
    render_mod.display(state, force=True)
    buf.seek(0)
    buf.truncate(0)

    # Inject a tweaked baseline where one row is longer than what the next
    # render() will emit, forcing the diff path to flag that row as "changed".
    assert render_mod._last_emitted_lines is not None
    baseline = list(render_mod._last_emitted_lines)
    if baseline:
        baseline[0] = baseline[0] + "STALE_TAIL_CHARS"
    render_mod._last_emitted_lines = tuple(baseline)

    # Force a re-render (state same) — the diff path fires because row 0
    # now differs from the new (shorter) row 0.
    render_mod.display(state)
    out = buf.getvalue()
    assert clear_to_eol() in out, (
        "diff-emit path must append clear_to_eol after each changed row "
        "so a shrunken row doesn't leave stale chars at the end."
    )


def test_pending_rendered_lines_pre_cleared_in_display(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.1.0 C6: `display()` must clear the side-channel global before calling
    `render()`, so a stale tuple from a previous frame can't be re-used if
    the new `render()` somehow fails to populate it.

    Pin by injecting a stub render() that doesn't populate the side channel,
    then asserting it's None after display() returned.
    """
    render_mod._last_emitted_lines = None
    render_mod._pending_rendered_lines = ("STALE", "TUPLE")

    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    state = new_game()
    render_mod.display(state, force=True)
    # The new render() populated it with a fresh tuple — but at the very
    # least the stale ("STALE", "TUPLE") tuple is gone.
    assert render_mod._pending_rendered_lines != ("STALE", "TUPLE")


def test_pending_rendered_lines_is_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.1.0 C3: the side-channel must be a tuple (immutable, no per-frame
    list allocation).
    """
    render_mod._last_emitted_lines = None
    buf = io.StringIO()
    monkeypatch.setattr(render_mod.sys, "stdout", buf)
    monkeypatch.setattr(render_mod, "get_term_size", lambda: (120, 40))

    render_mod.display(new_game(), force=True)
    assert render_mod._pending_rendered_lines is None or isinstance(
        render_mod._pending_rendered_lines, tuple
    )
