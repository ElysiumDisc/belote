"""3.9.4 felt-mat polish: braille pip overlay determinism, vignette, and
frame gating by terminal size.
"""

from __future__ import annotations

import sys as _sys

import pytest

import belote.ui.render  # noqa: F401  — ensures the module is imported
from belote.deck import Suit, make_deck, shuffle
from belote.game import GameState, Phase, Seat

render_mod = _sys.modules["belote.ui.render"]


def _state() -> GameState:
    import random
    deck = shuffle(make_deck(), random.Random(42))
    hands = tuple(tuple(deck[i * 8:(i + 1) * 8]) for i in range(4))
    return GameState(
        hands=hands,
        initial_hands=hands,
        taker=Seat.SOUTH,
        trump=Suit.SPADES,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
    )


def _render(size: tuple[int, int], *, selection: int | None = None) -> str:
    from belote.context import TERMINAL
    TERMINAL._size_cache = size
    return render_mod.render(_state(), selection=selection)


# ── Pip overlay determinism ───────────────────────────────────────────────


def test_pip_overlay_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render-diff correctness: two renders of the same state must be byte-
    identical. If pip placement ever uses random/time, this will fail."""
    render_mod._last_emitted_lines = None
    render_mod._last_render_key = None
    first = _render((96, 38))
    second = _render((96, 38))
    assert first == second


def test_pip_overlay_uses_braille_glyphs() -> None:
    """The felt should carry at least a few U+2800–U+28FF braille texture
    glyphs when UTF-8 is on (which it is in the test runner)."""
    out = _render((96, 38))
    has_braille = any(chr(c) in out for c in range(0x2800, 0x2900))
    assert has_braille, "expected braille texture in felt mat"


# ── Vignette ──────────────────────────────────────────────────────────────


def test_vignette_uses_felt_edge_bg() -> None:
    """The felt mat should contain at least one occurrence of felt_edge_bg
    (the darker vignette tone) — otherwise the vignette isn't being applied."""
    from belote.themes import THEMES, theme_manager
    edge = THEMES[theme_manager.current_name].felt_edge_bg
    out = _render((96, 38))
    expected = f"\x1b[48;2;{edge[0]};{edge[1]};{edge[2]}m"
    assert expected in out, "felt_edge_bg ANSI sequence missing from rendered felt"


# ── Decorative frame gating ───────────────────────────────────────────────


def _has_decorative_frame(out: str) -> bool:
    """Frame uses corner-ornamented top/bottom: `╔═══◆`. Card-art `◆` (Ace
    wreath) is always surrounded by `─`/`╮`, not `═`, so this combo is unique
    to the trick-mat frame."""
    return "╔══" in out and "◆══" in out


def test_frame_suppressed_at_compact() -> None:
    """COMPACT (80x32) has zero row budget for the frame."""
    out = _render((80, 32))
    assert not _has_decorative_frame(out)


def test_frame_suppressed_at_standard_minimum() -> None:
    """STANDARD min is 38; the frame needs +2 slack, so 38 itself gets no frame."""
    out = _render((96, 38))
    assert not _has_decorative_frame(out)


def test_frame_appears_with_slack() -> None:
    """At STANDARD with 2+ rows of headroom, the frame should appear."""
    out = _render((96, 40))
    assert _has_decorative_frame(out)


# ── Hand UI readout gating ────────────────────────────────────────────────


def test_hand_readout_appears_with_slack() -> None:
    """The card-name readout (► ... ◄) should appear when terminal has slack.

    Use a generously large terminal so the south hand isn't truncated by
    vcenter (which clips at term_h). The readout is the last hand row, so
    it's first to go when content overflows."""
    out = _render((140, 60), selection=0)
    assert "►" in out and "◄" in out


def test_hand_readout_suppressed_at_layout_minimum() -> None:
    """At a layout's exact min_rows, the readout should be suppressed so the
    south hand isn't pushed off the bottom."""
    out = _render((80, 32), selection=0)
    assert "►" not in out
