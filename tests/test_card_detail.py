"""4.0.0 Grimaud detail view: shape, per-card distinctness, key routing,
diff-baseline invalidation, and bid-phase up-card inspection.

See `src/belote/ui/card_detail.py` and the plan file
`/home/mrrobot/.claude/plans/home-mrrobot-belote-grimaud-standard-pl-twinkling-waffle.md`
for the design and bug history (the "two stacks of cards" issue is pinned
by `test_show_card_detail_invalidates_diff_baseline`).
"""

from __future__ import annotations

import re
import sys

import pytest

from belote.deck import Card, Rank, Suit, make_deck
from belote.input import Key, KeyEvent
from belote.ui.card_detail import (
    _FACE_DESIGNS,
    CARD_H,
    CARD_W,
    _face_lines,
    _render_card,
    show_card_detail,
)

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _vis(s: str) -> int:
    """Visible width of a string after stripping ANSI escape sequences."""
    return len(ANSI.sub("", s))


class _FakeReader:
    """Reader stub that immediately returns ENTER, dismissing the popup."""

    def read(self) -> KeyEvent:
        return KeyEvent(Key.ENTER)

    def read_timeout(self, _t: float) -> KeyEvent | None:
        return None


def test_every_card_renders_correct_shape() -> None:
    """All 32 cards must render exactly CARD_H rows of CARD_W visible cells."""
    for card in make_deck():
        rows = _render_card(card)
        assert len(rows) == CARD_H, f"{card}: got {len(rows)} rows, expected {CARD_H}"
        for i, row in enumerate(rows):
            assert _vis(row) == CARD_W, (
                f"{card} row {i}: visible width {_vis(row)} != {CARD_W}"
            )


def test_face_card_designs_complete_and_distinct() -> None:
    """All 12 (rank, suit) face combinations must have a distinct rendering."""
    keys = list(_FACE_DESIGNS.keys())
    assert len(keys) == 12, f"expected 12 face designs, got {len(keys)}"

    rendered: dict[tuple[Rank, Suit], tuple[str, ...]] = {}
    for rank, suit in keys:
        rendered[(rank, suit)] = tuple(_face_lines(Card(suit=suit, rank=rank)))

    seen: dict[tuple[str, ...], tuple[Rank, Suit]] = {}
    for key, lines in rendered.items():
        assert lines not in seen, f"{key} duplicates {seen[lines]}"
        seen[lines] = key


def test_card_detail_key_enum_exists() -> None:
    """Key.CARD_DETAIL must exist so the 'f' binding has somewhere to land."""
    assert Key.CARD_DETAIL.value == "CARD_DETAIL"


def test_show_card_detail_dismisses_on_any_key(capsys: pytest.CaptureFixture[str]) -> None:
    """show_card_detail must return cleanly after a single reader.read()."""
    show_card_detail(Card(Suit.HEARTS, Rank.QUEEN), _FakeReader())  # type: ignore[arg-type]
    out = capsys.readouterr().out
    # The popup wrote *something* to stdout (title, body, footer).
    assert "QUEEN OF HEARTS" in ANSI.sub("", out)
    assert "Grimaud Standard 1898" in ANSI.sub("", out)
    assert "any key" in ANSI.sub("", out)


def test_show_card_detail_invalidates_diff_baseline() -> None:
    """REGRESSION: pinning the "two stacks of cards" fix.

    The popup writes directly to stdout, bypassing render.display(). On
    dismiss, it MUST reset the render-diff baseline (`_last_emitted_lines`)
    so the next display() call emits a full frame. Without this, the next
    display() would diff against the pre-popup cached frame, see no row
    changes, and write nothing — leaving the popup visible.
    """
    render_mod = sys.modules["belote.ui.render"]
    render_mod._last_emitted_lines = ["sentinel-row"]
    show_card_detail(Card(Suit.SPADES, Rank.KING), _FakeReader())  # type: ignore[arg-type]
    assert render_mod._last_emitted_lines is None
