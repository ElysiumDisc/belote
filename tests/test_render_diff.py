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
