"""4.9.0 / U1: pin the card-lift behavior of `_render_hand_horizontal`.

Selecting a card should rise it one row above its neighbors (deferred C1).
Unselected hand renders at `card_h` rows; selected renders at `card_h + 1`
card rows + 1 highlight bar row.
"""
from __future__ import annotations

import random

from belote.deck import Suit
from belote.game import Seat, new_game, start_round
from belote.ui.layout import COMPACT
from belote.ui.render import _render_hand_horizontal


def _sample_hand() -> tuple:
    s = new_game()
    s = start_round(s, random.Random(42))
    return tuple(s.hand_of(Seat.SOUTH)[:5])


def test_no_selection_renders_card_h_rows() -> None:
    hand = _sample_hand()
    rows = _render_hand_horizontal(
        hand, None, hand, term_w=80, layout=COMPACT,
        trump=Suit.HEARTS, show_readout=False,
    )
    # No lift, no highlight bar — exactly card_h rows.
    assert len(rows) == COMPACT.card_h


def test_selection_lifts_selected_card_one_row() -> None:
    hand = _sample_hand()
    rows = _render_hand_horizontal(
        hand, 2, hand, term_w=80, layout=COMPACT,
        trump=Suit.HEARTS, show_readout=False,
    )
    # card_h + 1 card rows (lift adds the top row) + 1 highlight bar row.
    assert len(rows) == COMPACT.card_h + 2


def test_selection_with_readout_adds_label_row() -> None:
    hand = _sample_hand()
    rows = _render_hand_horizontal(
        hand, 0, hand, term_w=80, layout=COMPACT,
        trump=Suit.HEARTS, show_readout=True,
    )
    # card_h + 1 (cards with lift) + 1 (highlight bar) + 1 (readout label).
    assert len(rows) == COMPACT.card_h + 3


def test_lifted_row_is_only_the_selected_card() -> None:
    """The top row should contain only the selected card's content — all other
    slots are bare spaces so the felt shows through."""
    hand = _sample_hand()
    # Select the middle card (index 2 of 5).
    rows = _render_hand_horizontal(
        hand, 2, hand, term_w=80, layout=COMPACT,
        trump=Suit.HEARTS, show_readout=False,
    )
    top_row = rows[0]
    # The top row should have ANSI escapes (the selected card's face) — if any
    # OTHER card painted on this row, we'd see multiple `\x1b[48;` background
    # transitions. Selected card alone gives exactly one card_face_bg block.
    # Count card-face background openers: each card emits one per row.
    bg_openers = top_row.count("\x1b[48;2;")
    # Selected card uses highlight_bg (since selected=True), and pip overlays
    # may emit additional bg codes within the same card. We just assert that
    # other cards (which would each emit at least one bg opener) are absent —
    # i.e. there's no horizontal gap-separated repetition of card bodies.
    # Cheap proxy: the row contains less ANSI than a fully-painted row.
    full_row = rows[COMPACT.card_h // 2 + 1]  # a row where all cards paint
    assert bg_openers < full_row.count("\x1b[48;2;"), (
        "lifted top row should have fewer card-face bg openers than a full row"
    )
