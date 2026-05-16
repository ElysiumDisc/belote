"""4.1.0 C5: `show_history` caches its line list across scroll iterations.

Pre-4.1.0 the full lines list was rebuilt on every keystroke. The 4.1.0
refactor extracts the line-building into `_build_history_lines(state, term_w)`
and caches the result keyed by `(term_w, len(state.score_history))` — state
is immutable during the modal so the cache is always coherent.

These tests pin (1) the helper produces lines for both wide/narrow layouts
and an empty history, and (2) the cache invariant by counting calls to the
helper when the user scrolls within the modal.
"""

from __future__ import annotations

import sys as _sys
from typing import Any

import pytest

import belote.ui.prompts  # noqa: F401 — ensure module is imported
from belote.game import RoundScore, Seat, new_game
from belote.input import Key, KeyEvent

prompts_mod = _sys.modules["belote.ui.prompts"]


def _round_score(idx: int) -> RoundScore:
    return RoundScore(
        taker_team=0,
        ns_card_pts=82,
        ew_card_pts=80,
        ns_decl_pts=0,
        ew_decl_pts=0,
        ns_belote_pts=0,
        ew_belote_pts=0,
        ns_rebelote=False,
        ew_rebelote=False,
        ns_total=82,
        ew_total=80,
        is_failed=False,
        is_capot=False,
        taker_seat=Seat.SOUTH,
        tricks_ns=5,
        tricks_ew=3,
    )


def test_build_history_lines_empty() -> None:
    """With no rounds played, the helper still produces a valid lines list."""
    state = new_game()
    lines = prompts_mod._build_history_lines(state, term_w=120)
    assert any("GAME HISTORY" in ln for ln in lines)
    assert any("No rounds completed yet" in ln for ln in lines)


def test_build_history_lines_wide_layout() -> None:
    """At term_w ≥ 78 the helper uses the single-row wide layout."""
    state = new_game()
    state = state.__class__(**{**state.__dict__, "score_history": tuple(_round_score(i) for i in range(3))}) \
        if hasattr(state, "__dict__") else state
    # GameState is frozen+slotted, so build via dataclasses.replace
    import dataclasses

    state = dataclasses.replace(state, score_history=tuple(_round_score(i) for i in range(3)))
    lines = prompts_mod._build_history_lines(state, term_w=120)
    assert any("CONTRACT" in ln for ln in lines), "wide layout must show CONTRACT header"


def test_build_history_lines_narrow_layout() -> None:
    """At term_w < 78 the helper uses the compact two-line-per-round layout."""
    import dataclasses

    state = new_game()
    state = dataclasses.replace(state, score_history=tuple(_round_score(i) for i in range(2)))
    lines = prompts_mod._build_history_lines(state, term_w=60)
    # Narrow layout uses 'CON' (compact) instead of 'CONTRACT'.
    assert any("CON" in ln for ln in lines)
    assert not any("CONTRACT" in ln for ln in lines), (
        "narrow layout must NOT use the wide-layout CONTRACT header"
    )


def test_show_history_caches_lines_across_scroll(monkeypatch: pytest.MonkeyPatch) -> None:
    """C5 invariant: pressing ↓ then a dismiss key must build the lines tuple
    only once — the cache key (term_w, history_len) is stable across the
    scroll. Pre-4.1.0 the rebuild fired on every keystroke.
    """
    import dataclasses

    state = new_game()
    state = dataclasses.replace(state, score_history=tuple(_round_score(i) for i in range(5)))

    # Stub stdout so the overlay can write without polluting test output.
    class _DevNull:
        def write(self, *_args: Any, **_kwargs: Any) -> int:
            return 0

        def flush(self) -> None:
            pass

    monkeypatch.setattr(prompts_mod.sys, "stdout", _DevNull())
    monkeypatch.setattr(prompts_mod, "get_term_size", lambda: (120, 40))
    monkeypatch.setattr(prompts_mod, "_history_override", None)

    call_count = 0
    original = prompts_mod._build_history_lines

    def _counting_build(state: Any, term_w: int) -> list[str]:
        nonlocal call_count
        call_count += 1
        return original(state, term_w)

    monkeypatch.setattr(prompts_mod, "_build_history_lines", _counting_build)

    # Simulate user pressing ↓, ↓, then any-key-dismiss.
    keys = iter([
        KeyEvent(Key.DOWN),
        KeyEvent(Key.DOWN),
        KeyEvent(Key.QUIT),
    ])

    class _Reader:
        def read(self) -> KeyEvent:
            return next(keys)

    prompts_mod.show_history(state, _Reader())
    assert call_count == 1, (
        f"_build_history_lines was called {call_count} times across 3 scroll "
        f"keystrokes — the cache (term_w, history_len) key isn't holding."
    )
