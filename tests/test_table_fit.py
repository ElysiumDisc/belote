"""4.11.0: the classic table always fits the terminal, and incremental card
patches land exactly where a full render draws the card."""

from __future__ import annotations

import io
import itertools
import random
import re
import sys
from dataclasses import replace

import pytest

import belote.ui.render  # noqa: F401 — the function `belote.ui.render` shadows it
from belote.context import TERMINAL
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard, new_game, place_bid, start_round
from belote.ui.cards import _get_card_face
from belote.ui.layout import MINI, fit_table

R = sys.modules["belote.ui.render"]
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _states() -> tuple[GameState, GameState]:
    deal = start_round(new_game(), random.Random(7))
    play = deal
    while play.phase == Phase.BIDDING:
        play = place_bid(play, Suit.SPADES if play.turn == Seat.SOUTH else None)
    return replace(deal, turn=Seat.SOUTH), play


@pytest.fixture
def term(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def set_size(cols: int, rows: int) -> None:
        monkeypatch.setattr(TERMINAL, "_size_cache", (cols, rows))
        monkeypatch.setattr(R, "_last_render_key", None)

    return set_size


@pytest.mark.parametrize("cols", [80, 96, 120, 160])
def test_table_never_taller_than_the_terminal(term, cols: int) -> None:  # type: ignore[no-untyped-def]
    bid, play = _states()
    for rows in range(24, 64):
        term(cols, rows)
        for state, kw in ((bid, {"bid_selection": 0}), (play, {"selection": 0})):
            frame = R.render(state, **kw)
            assert R._last_rendered_unpadded_h <= rows, (cols, rows, state.phase)
            body = _ANSI.sub("", frame.split("\x1b[?25l", 1)[-1])
            assert "You" in body  # SOUTH's label (last row) is on screen
            if state is bid:
                assert "Bid:" in body  # the bid selector is on screen


@pytest.mark.parametrize("size", [(80, 24), (80, 32), (100, 40), (120, 40), (120, 52), (160, 60)])
@pytest.mark.parametrize("seat", list(Seat))
def test_patch_lands_where_render_draws(term, size, seat: Seat) -> None:  # type: ignore[no-untyped-def]
    term(*size)
    _, play = _states()
    card = play.hand_of(seat)[0]
    state = replace(play, current_trick=(TrickCard(seat, card),))
    lines = [_ANSI.sub("", ln) for ln in R.render(state).split("\r\n")]
    geo = R._last_mat_geometry
    assert geo is not None
    top = _ANSI.sub("", _get_card_face(card, layout=geo.fit.layout)[0]).strip()
    drawn = [(i + 1, ln.index(top) + 1) for i, ln in enumerate(lines) if top in ln]
    buf = io.StringIO()
    old, sys.stdout = sys.stdout, buf
    try:
        R.patch_trick_card(state, seat, card)
    finally:
        sys.stdout = old
    m = re.search(r"\x1b\[(\d+);(\d+)H", buf.getvalue())
    assert m is not None
    assert (int(m.group(1)), int(m.group(2))) in drawn


def test_patch_after_resize_falls_back_to_a_full_frame(term, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    term(120, 40)
    _, play = _states()
    R.render(play)
    term(80, 24)
    shown: list[GameState] = []
    monkeypatch.setattr(R, "display", lambda s, *_a, **_k: shown.append(s))
    R.patch_trick_card(play, Seat.EAST, play.hand_of(Seat.EAST)[0])
    assert shown == [play]


def test_mini_card_face_is_three_rows_with_rank_and_suit() -> None:
    face = _get_card_face(Card(Suit.HEARTS, Rank.TEN), layout=MINI)
    assert len(face) == 3
    assert "10♥" in _ANSI.sub("", face[1])


def test_up_card_is_centred_and_east_stays_right(term) -> None:  # type: ignore[no-untyped-def]
    term(160, 50)
    bid, _ = _states()
    lines = [_ANSI.sub("", ln) for ln in R.render(bid, bid_selection=0).split("\r\n")]
    up = next(ln for ln in lines if "UP CARD" in ln)
    centre = up.index("UP CARD") + len("UP CARD") // 2
    assert abs(centre - 80) <= 2
    east = next(ln for ln in lines if "East" in ln)
    assert east.index("East") >= 160 - fit_table(160, 50).layout.side_col_w


def test_hand_numbers_sit_over_their_cards(term) -> None:  # type: ignore[no-untyped-def]
    term(120, 40)
    _, play = _states()
    lines = [_ANSI.sub("", ln) for ln in R.render(play).split("\r\n")]
    nums = next(ln for ln in lines if "[1]" in ln and "[8]" in ln)
    layout = fit_table(120, 40).layout
    slot = layout.card_w + layout.card_gap
    starts = [nums.index(f"[{i + 1}]") for i in range(8)]
    assert all(b - a == slot for a, b in itertools.pairwise(starts))


@pytest.fixture
def overlays():  # type: ignore[no-untyped-def]
    R.set_overlay_provider(lambda: (5, 6))  # BelAtro's HUD: rows 1-5, last 6
    yield
    R.set_overlay_provider(None)


@pytest.mark.parametrize("size", [(80, 32), (100, 38), (120, 40), (160, 50)])
def test_expansion_overlay_rows_stay_clear(term, overlays, size) -> None:  # type: ignore[no-untyped-def]
    """4.11.0: BelAtro's top HUD and bottom score tally paint over fixed rows;
    the table is fitted into the window between them."""
    cols, rows = size
    term(cols, rows)
    bid, play = _states()
    for state, kw in ((bid, {"bid_selection": 0}), (play, {"selection": 0})):
        frame = R.render(state, **kw)
        lines = [_ANSI.sub("", ln).strip() for ln in frame.split("\r\n")]
        assert len(lines) == rows
        assert lines[2:5] == ["", "", ""]  # under the top overlay (rows 3-5)
        assert lines[-6:] == [""] * 6  # under the score tally + last row
        assert any("You" in ln for ln in lines)


@pytest.mark.parametrize("seat", list(Seat))
def test_patch_lands_correctly_under_overlays(term, overlays, seat: Seat) -> None:  # type: ignore[no-untyped-def]
    test_patch_lands_where_render_draws(term, (120, 40), seat)
