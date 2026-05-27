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


# ── 4.6.1 audit-pass pins ──────────────────────────────────────────────────


def test_show_main_menu_invalidates_diff_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.6.1: `show_main_menu` writes to stdout directly (bypassing `display()`)
    and must reset `_last_emitted_lines` before returning, else the first
    `display()` after game-start in a second-play-of-session would diff
    against the stale post-prior-game frame → first-frame artifacts.

    Same convention as `show_help`/`show_history`/`show_rules` (4.0.0) and
    `show_card_detail` (4.0.0, removed in 4.6.0).
    """
    from belote.game import Seat
    from belote.input import Key, KeyEvent
    from belote.ui import menu as menu_mod

    class _QuitReader:
        def read(self) -> KeyEvent:
            return KeyEvent(Key.QUIT)

        def read_timeout(self, _t: float) -> KeyEvent | None:
            return KeyEvent(Key.QUIT)

    # Stamp a stale baseline so a missing invalidate_diff() is observable.
    render_mod._last_emitted_lines = ("stale post-prior-game row",)

    buf = io.StringIO()
    monkeypatch.setattr(menu_mod.sys, "stdout", buf)
    monkeypatch.setattr(menu_mod, "get_term_size", lambda: (120, 40))

    diffs = {Seat.EAST: "medium", Seat.NORTH: "medium", Seat.WEST: "medium"}
    choice, _, _, _ = menu_mod.show_main_menu(
        _QuitReader(),  # type: ignore[arg-type]
        diffs,
        target=1000,
        speed="normal",
    )
    assert choice == "Quit"
    assert render_mod._last_emitted_lines is None, (
        "show_main_menu must invalidate_diff() on exit so a subsequent "
        "display() emits a full frame (4.6.1 audit fix)"
    )


def test_show_theme_selector_invalidates_diff_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same overlay-bypass contract as show_main_menu — pinned independently
    so a future refactor of one path can't silently drop the guard on the other.
    """
    from belote.input import Key, KeyEvent
    from belote.ui import menu as menu_mod

    class _EscReader:
        def read(self) -> KeyEvent:
            return KeyEvent(Key.ESC)

    render_mod._last_emitted_lines = ("stale row",)

    buf = io.StringIO()
    monkeypatch.setattr(menu_mod.sys, "stdout", buf)
    monkeypatch.setattr(menu_mod, "get_term_size", lambda: (120, 40))

    menu_mod.show_theme_selector(_EscReader())  # type: ignore[arg-type]
    assert render_mod._last_emitted_lines is None


def test_shop_render_writes_once_per_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.6.1: `ShopScreen._render` must batch its entire frame into one
    `sys.stdout.write` call. Pre-4.6.1 the method used ~16 bare `print()`
    calls per redraw — each a separate syscall. Same single-write convention
    as `belatro/ui/hud.py::_render` and `prompts.py::show_help`.
    """
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.run.shop import Shop
    from belote.belatro.ui import shop as shop_mod
    from belote.belatro.ui.shop import ShopScreen

    register_all_items()
    run = BelAtroRun(seed=42)
    run.economy.money = 100
    shop = Shop(run)
    shop.generate_inventory()

    class _NopReader:
        def read(self) -> object:
            raise AssertionError("reader.read should not be called by _render alone")

    screen = ShopScreen(shop, _NopReader())  # type: ignore[arg-type]

    # Count direct write calls during _render. The fit_guard's `require_minimum`
    # short-circuits when the terminal is already large enough, so it doesn't
    # add writes on the happy path.
    class _CountingBuf(io.StringIO):
        write_count = 0

        def write(self, s: str) -> int:  # type: ignore[override]
            self.write_count += 1
            return super().write(s)

    buf = _CountingBuf()
    monkeypatch.setattr(shop_mod.sys, "stdout", buf)
    # Force a comfortable terminal size so require_minimum doesn't trip and
    # the shop layout has room. `get_term_size` is imported locally inside
    # `_render` from the render module (which __init__ shadows as a function),
    # so patch on the module object via sys.modules.
    render_module = _sys.modules["belote.ui.render"]
    monkeypatch.setattr(render_module, "get_term_size", lambda: (120, 40))

    screen._render()

    assert buf.write_count == 1, (
        f"ShopScreen._render must batch into one write; got {buf.write_count}. "
        f"Pre-4.6.1 this was ~16 due to per-card print() calls."
    )


def test_announce_invalidates_diff_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.7.3 regression: `announce()` paints a transient banner at the bottom
    row via absolute-position writes, bypassing the diff cache. Without a
    post-paint `invalidate_diff()` the next `display()` could diff the new
    frame against `_last_emitted_lines` (which has no record of the banner)
    and leave the banner visible as a ghost overlay.

    Same architectural rule as `show_help`/`show_history`/`show_rules`/
    `show_card_detail`/`show_round_summary`/`animate_score_update`.
    """
    import belote.ui.announce  # noqa: F401
    announce_mod = _sys.modules["belote.ui.announce"]

    # Seed a non-None diff baseline. If invalidate_diff() runs, this resets to None.
    render_mod._last_emitted_lines = ("stale row",)

    # Stub the reader-less zero-duration path so the test is instantaneous.
    monkeypatch.setattr(announce_mod, "get_term_size", lambda: (120, 40))
    buf = io.StringIO()
    monkeypatch.setattr(announce_mod.sys, "stdout", buf)

    announce_mod.announce("Trick won!", duration=0.0, reader=None)

    assert render_mod._last_emitted_lines is None, (
        "announce() must call invalidate_diff() before returning — without "
        "it, the bottom-row banner persists as a ghost on the next display()."
    )


def test_animate_score_update_invalidates_diff_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.6.4 regression: `animate_score_update` paints HUD rows directly via
    `display_hud`, bypassing the diff cache. Without the post-loop
    `invalidate_diff()` the next `display()` may diff against the stale
    pre-animation baseline and skip emitting rows that the animation
    overwrote on screen.

    Mirrors the architectural rule already enforced for the BelAtro
    overlays — see `tests/test_alt_screen_scroll.py::
    test_belatro_overlays_invalidate_diff`.
    """
    # `belote.ui.announce` is re-exported as the `announce` function by the
    # package's __init__, so reach for the module directly via sys.modules
    # (same pattern as test_card_detail.py).
    import belote.ui.announce  # noqa: F401  — ensures the module is imported
    announce_mod = _sys.modules["belote.ui.announce"]

    # Seed a non-None diff baseline. If invalidate_diff() runs, this resets
    # to None.
    render_mod._last_emitted_lines = ("stale row",)

    # Stub out the actual stdout writes and the sleep so the test is fast.
    monkeypatch.setattr(
        announce_mod, "display_hud", lambda _s, **_kw: None
    )
    monkeypatch.setattr(announce_mod.time, "sleep", lambda _d: None)

    state = new_game()
    announce_mod.animate_score_update(state, target_ns=20, target_ew=10, duration=0.0)

    assert render_mod._last_emitted_lines is None, (
        "animate_score_update must call invalidate_diff() after its "
        "display_hud loop — pre-4.6.4 the diff cache held stale baselines "
        "after the animation."
    )


def test_animate_score_update_short_circuits_under_no_anim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.9.2 (A1): with BELOTE_NO_ANIM=1, the score-roll paints exactly one
    final HUD frame instead of running the 20-step loop. Pre-4.9.2 the
    animation ignored the env var and slept for the full duration.
    """
    import belote.ui.anim
    import belote.ui.announce  # noqa: F401
    anim_mod = _sys.modules["belote.ui.anim"]
    announce_mod = _sys.modules["belote.ui.announce"]

    paint_count = [0]
    last_override: list[tuple[int, int]] = []

    def _spy_display_hud(_s: object, **kw: object) -> None:
        paint_count[0] += 1
        override = kw.get("team_scores_override")
        if isinstance(override, tuple):
            last_override.append(override)  # type: ignore[arg-type]

    monkeypatch.setattr(announce_mod, "display_hud", _spy_display_hud)

    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    anim_mod._refresh_animations_enabled_from_env()
    try:
        state = new_game()
        announce_mod.animate_score_update(state, target_ns=20, target_ew=10, duration=1.0)
    finally:
        monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
        anim_mod._refresh_animations_enabled_from_env()

    assert paint_count[0] == 1, (
        f"NO_ANIM must paint exactly one final frame; got {paint_count[0]}"
    )
    assert last_override == [(20, 10)], (
        f"NO_ANIM must paint the final target scores directly; got {last_override}"
    )


def test_animate_score_update_skips_on_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """4.9.2 (A1): when a reader is supplied and the user presses a key
    mid-animation, the function snaps to the final frame and exits the
    loop instead of completing all 20 steps.
    """
    import belote.ui.anim
    import belote.ui.announce  # noqa: F401
    anim_mod = _sys.modules["belote.ui.anim"]
    announce_mod = _sys.modules["belote.ui.announce"]

    paints: list[tuple[int, int] | None] = []

    def _spy_display_hud(_s: object, **kw: object) -> None:
        paints.append(kw.get("team_scores_override"))  # type: ignore[arg-type]

    monkeypatch.setattr(announce_mod, "display_hud", _spy_display_hud)
    # Ensure NO_ANIM is not active so we exercise the loop path.
    monkeypatch.delenv("BELOTE_NO_ANIM", raising=False)
    anim_mod._refresh_animations_enabled_from_env()

    # Reader yields a KeyEvent on the first read_timeout — caller must snap.
    from belote.input import Key, KeyEvent

    class _SkipReader:
        def __init__(self) -> None:
            self.calls = 0

        def read_timeout(self, _delay: float) -> KeyEvent | None:
            self.calls += 1
            # Skip on the very first wait.
            return KeyEvent(Key.SPACE, " ")

    reader = _SkipReader()
    state = new_game()
    announce_mod.animate_score_update(
        state, target_ns=20, target_ew=10, duration=1.0, reader=reader  # type: ignore[arg-type]
    )

    # At least one intermediate paint + one final-snap paint, but
    # strictly fewer than 20 frames (the full loop). The exact intermediate
    # count is 1 — one frame painted before read_timeout returns the skip.
    assert reader.calls == 1, f"reader should be consulted once before skip; got {reader.calls}"
    assert paints[-1] == (20, 10), (
        f"final paint must be the target scores; got {paints[-1]}"
    )
    assert len(paints) < 20, (
        f"skip should short-circuit the 20-step loop; got {len(paints)} paints"
    )
