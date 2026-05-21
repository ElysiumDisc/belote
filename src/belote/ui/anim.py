"""Small animation toolkit shared by classic Belote and BelAtro UI.

Three architectural rules every helper here MUST follow (these are pinned by
existing render-diff tests; violating them produces 'ghost frame' bugs like
the 4.0.0 'two stacks of cards' regression):

1. Paint with absolute cursor positioning via `move(row, col)` — never write
   raw `\\r\\n` (scrolls the alt-screen on strict emulators) and never use
   the high-level `display()` (its diff cache would skip our intermediate
   frames).
2. Always end with `invalidate_diff()` in a `finally` block so the next
   `display()` re-emits a full frame on top of whatever we painted.
3. Route delays through `interruptible_sleep(duration, reader)` so any
   keypress collapses the animation immediately. Fall back to `time.sleep`
   only when no reader is available (the rare non-interactive call site).

Environment kill switch: `BELOTE_NO_ANIM=1` short-circuits every helper to
its end-state with no perceptible delay. Independent from `BELOTE_NO_DIFF`
so each lever can be flipped separately during debugging.
"""
from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

from ..ansi import clear_line, move
from ..input import KeyEvent, KeyReader
from .render import invalidate_diff

_ANIMATIONS_ENABLED = os.environ.get("BELOTE_NO_ANIM") != "1"


def animations_enabled() -> bool:
    """True unless `BELOTE_NO_ANIM=1` is set in the environment.

    Cached at import. Callers should branch on this to either run the full
    animation or paint a single end-state frame and return immediately.
    """
    return _ANIMATIONS_ENABLED


def _refresh_animations_enabled_from_env() -> None:
    """Test-only: re-read the env var after `monkeypatch.setenv`."""
    global _ANIMATIONS_ENABLED
    _ANIMATIONS_ENABLED = os.environ.get("BELOTE_NO_ANIM") != "1"


# ── Easing helpers ────────────────────────────────────────────────────────
# Pure numeric, no I/O. All take `t ∈ [0, 1]` and return `[0, 1]`.

def ease_out_quad(t: float) -> float:
    """Decelerating ease — fast start, slow finish."""
    return 1 - (1 - t) * (1 - t)


def ease_in_out_quad(t: float) -> float:
    """Symmetric ease — slow start, fast middle, slow finish."""
    if t < 0.5:
        return 2 * t * t
    return 1 - 2 * (1 - t) * (1 - t)


def ease_out_cubic(t: float) -> float:
    """Stronger deceleration than quad — feels 'snappier'."""
    u = 1 - t
    return 1 - u * u * u


# ── Painted-frame helpers ─────────────────────────────────────────────────


def pulse_text(
    row: int,
    col: int,
    text: str,
    *,
    frames: int = 6,
    frame_delay: float = 0.05,
    reader: KeyReader | None = None,
    colors: tuple[str, ...] | None = None,
) -> KeyEvent | None:
    """Pulse `text` at `(row, col)` over `frames`, cycling through `colors`.

    If `colors` is None, alternates BOLD / DIM with the terminal's default
    foreground. Returns the `KeyEvent` if the user pressed a key to skip,
    otherwise None. Always calls `invalidate_diff()` on exit.
    """
    if not _ANIMATIONS_ENABLED:
        sys.stdout.write(move(row, col) + text)
        sys.stdout.flush()
        invalidate_diff()
        return None

    from ..ansi import BOLD, DIM, RESET

    palette: tuple[str, ...] = colors if colors is not None else (BOLD, DIM)
    try:
        for i in range(frames):
            prefix = palette[i % len(palette)]
            sys.stdout.write(move(row, col) + prefix + text + RESET)
            sys.stdout.flush()
            if reader is not None:
                # read_timeout (not interruptible_sleep) so test stubs that
                # override only `read_timeout` don't escape into the raw
                # select() path; matches the existing slot_machine_tally
                # idiom.
                event = reader.read_timeout(frame_delay)
                if event is not None:
                    return event
            else:
                time.sleep(frame_delay)
        return None
    finally:
        invalidate_diff()


def float_text(
    text: str,
    start_row: int,
    end_row: int,
    col: int,
    *,
    color: str = "",
    frames: int | None = None,
    frame_delay: float = 0.04,
    reader: KeyReader | None = None,
) -> KeyEvent | None:
    """Animate `text` drifting from `start_row` to `end_row` at `col`.

    The final frame paints DIM (fade-out cue) and then the path is cleared.
    `frames` defaults to `abs(end_row - start_row) + 1` (one row per frame).
    Returns the `KeyEvent` if a key was pressed to skip, otherwise None.
    """
    if not _ANIMATIONS_ENABLED:
        invalidate_diff()
        return None

    from ..ansi import DIM, RESET

    distance = abs(end_row - start_row)
    if frames is None:
        frames = distance + 1
    step = 1 if end_row >= start_row else -1
    rows_visited: list[int] = []
    try:
        for i in range(frames):
            t = i / max(1, frames - 1)
            offset = round(distance * ease_out_quad(t)) * step
            row = start_row + offset
            # Erase the previous frame's row before painting this one.
            if rows_visited and rows_visited[-1] != row:
                sys.stdout.write(move(rows_visited[-1], col) + clear_line())
            rows_visited.append(row)
            prefix = DIM if i == frames - 1 else color
            sys.stdout.write(move(row, col) + prefix + text + RESET)
            sys.stdout.flush()
            if reader is not None:
                event = reader.read_timeout(frame_delay)
                if event is not None:
                    return event
            else:
                time.sleep(frame_delay)
        return None
    finally:
        # Clear the trail so the next display() repaints over a blank canvas.
        for r in set(rows_visited):
            sys.stdout.write(move(r, col) + clear_line())
        sys.stdout.flush()
        invalidate_diff()


def tick_bar(
    old_value: int,
    new_value: int,
    *,
    render_fn: Callable[[int], None],
    frames: int = 12,
    frame_delay: float = 0.03,
    reader: KeyReader | None = None,
) -> KeyEvent | None:
    """Drive `render_fn(intermediate_value)` over `frames` from old → new.

    `render_fn` is responsible for painting the bar (or any other widget)
    at the given intermediate value; this helper just walks the value and
    paces the delay. Always calls `invalidate_diff()` on exit.
    """
    if not _ANIMATIONS_ENABLED:
        render_fn(new_value)
        invalidate_diff()
        return None

    try:
        if old_value == new_value:
            return None
        for i in range(1, frames + 1):
            t = i / frames
            val = round(old_value + (new_value - old_value) * ease_out_cubic(t))
            render_fn(val)
            if reader is not None:
                event = reader.read_timeout(frame_delay)
                if event is not None:
                    render_fn(new_value)
                    return event
            else:
                time.sleep(frame_delay)
        render_fn(new_value)
        return None
    finally:
        invalidate_diff()
