"""Golden full-frame render snapshot (4.9.6).

Regression guard for the wcwidth refactor in `belote.ansi` (visible_len now
measures terminal *cells*, not codepoints). The play state here is pure ASCII,
so the wcwidth change must leave the rendered frame byte-identical — these pins
prove it and freeze the frame against future accidental drift.

Pins:
* line count == terminal height,
* the per-row visible-*cell* width fingerprint (the alignment invariant the
  wcwidth change must preserve),
* a sha256 of the whole frame for total-change detection,
* render determinism (same inputs → same bytes).

The felt rows measure ``term_w + 1`` cells on purpose: the mat fills the final
column, relying on the terminal's pending-wrap (DECAWM) deferral so the extra
cell is painted without inserting a blank line. This is existing, intentional
behaviour — pinned, not "fixed".

If an intentional UI change moves the frame, re-pin the constants below from the
failure output rather than loosening the assertions.
"""

from __future__ import annotations

import hashlib
import random
import sys as _sys

import pytest

import belote.ui.render  # noqa: F401 — ensures the module object is importable
from belote.ansi import visible_len
from belote.deck import Suit
from belote.game import Phase, Seat, new_game, replace, start_round

render_mod = _sys.modules["belote.ui.render"]

# Fixed 120x40 terminal so the snapshot is deterministic regardless of host.
# Hashes are for the default `classic_green` theme; tests/conftest.py sandboxes
# HOME so a developer's saved theme.json can't leak into the render.
_TERM = (120, 40)

# Per-row visible cell widths for the seeded PLAYING frame at 120x40.
# 4.11.0: re-pinned on purpose — the old frame was 47 rows clipped to 40 (the
# bottom of the hand was cut off); the table is now fitted to the height.
_GOLDEN_WIDTHS = (
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    82,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    121,
    120,
)
_GOLDEN_SHA_SEL0 = "8317217d154d8ca5456a911a4050745ae0f7352655ac209db030c90960e090cb"
_GOLDEN_SHA_SEL3 = "a434766655587d606ab00b5da362b444cb74b740ad700944eb84f36c96050da2"


def _seeded_play_state() -> object:
    state = new_game()
    state = start_round(state, random.Random(42))
    return replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)


@pytest.fixture(autouse=True)
def _golden_term_size(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scoped: a bare module-attribute assignment leaked the 120x40 size into
    # every render test that ran after this file.
    monkeypatch.setattr(render_mod, "get_term_size", lambda: _TERM)


def _render(selection: int) -> str:
    return render_mod.render(_seeded_play_state(), selection=selection)


def test_golden_frame_line_count() -> None:
    frame = _render(0)
    assert len(frame.split("\n")) == _TERM[1]


def test_golden_frame_cell_widths() -> None:
    """The alignment fingerprint the wcwidth change must preserve."""
    frame = _render(0)
    widths = tuple(visible_len(line) for line in frame.split("\n"))
    assert widths == _GOLDEN_WIDTHS


def test_golden_frame_sha256() -> None:
    assert hashlib.sha256(_render(0).encode()).hexdigest() == _GOLDEN_SHA_SEL0
    assert hashlib.sha256(_render(3).encode()).hexdigest() == _GOLDEN_SHA_SEL3


def test_golden_frame_is_deterministic() -> None:
    assert _render(0) == _render(0)
