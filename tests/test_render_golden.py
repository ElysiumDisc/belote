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

import belote.ui.render  # noqa: F401 — ensures the module object is importable
from belote.ansi import visible_len
from belote.deck import Suit
from belote.game import Phase, Seat, new_game, replace, start_round

render_mod = _sys.modules["belote.ui.render"]

# Fixed 120x40 terminal so the snapshot is deterministic regardless of host.
_TERM = (120, 40)

# Per-row visible cell widths for the seeded PLAYING frame at 120x40.
_GOLDEN_WIDTHS = (
    121, 121, 121, 1, 121, 121, 121, 121, 121, 121,
    121, 121, 121, 121, 121, 121, 121, 121, 121, 121,
    121, 121, 121, 121, 121, 121, 121, 121, 121, 121,
    121, 121, 121, 121, 121, 121, 121, 121, 121, 120,
)
_GOLDEN_SHA_SEL0 = "05568b63dcd0d04b34c12c04444211afa69062a24c24a0ef38fe805973ece9f2"
_GOLDEN_SHA_SEL3 = "bae622bc7141e7acefea637de8bfe1f3af4d04354f3aed7893244bd4ac1a5ccd"


def _seeded_play_state() -> object:
    state = new_game()
    state = start_round(state, random.Random(42))
    return replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)


def _render(selection: int) -> str:
    render_mod.get_term_size = lambda: _TERM
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
