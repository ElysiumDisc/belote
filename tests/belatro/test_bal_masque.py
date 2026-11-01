"""4.11.0: Le Bal Masqué — opponents' first-trick cards are drawn face-down
until the trick is won (display only: rules and legal moves see the cards)."""

from __future__ import annotations

import io
import random
import re
import sys
from dataclasses import replace

import pytest

import belote.ui.render  # noqa: F401 — the function `belote.ui.render` shadows it
from belote.belatro.run.boss import ALL_BOSS_MODIFIERS, LeBalMasque
from belote.context import TERMINAL
from belote.deck import Suit
from belote.game import Phase, Seat, TrickCard, legal_cards, new_game, place_bid, start_round
from belote.ui.cards import _get_card_face
from belote.ui.table import masked_seats
from belote.variants import RuleVariants

R = sys.modules["belote.ui.render"]
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _play_state():  # type: ignore[no-untyped-def]
    s = start_round(new_game(), random.Random(3))
    while s.phase == Phase.BIDDING:
        s = place_bid(s, Suit.HEARTS if s.turn == Seat.SOUTH else None)
    return replace(s, variants=RuleVariants(masked_first_trick=True))


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def test_boss_registered_and_sets_the_flag() -> None:
    assert LeBalMasque in ALL_BOSS_MODIFIERS
    assert LeBalMasque().flags().masked_first_trick is True
    assert "normally public" in LeBalMasque.description


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_opponents_masked_during_trick_one_partner_not(monkeypatch, size) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(TERMINAL, "_size_cache", size)
    monkeypatch.setattr(R, "_last_render_key", None)
    s = _play_state()
    east, north = s.hand_of(Seat.EAST)[0], s.hand_of(Seat.NORTH)[0]
    trick = (TrickCard(Seat.EAST, east), TrickCard(Seat.NORTH, north))
    state = replace(s, current_trick=trick)
    assert masked_seats(state) == frozenset({Seat.EAST, Seat.WEST})
    frame = _plain(R.render(state))
    layout = R._last_mat_geometry.fit.layout
    east_face = _plain(_get_card_face(east, layout=layout)[1]).strip()
    north_face = _plain(_get_card_face(north, layout=layout)[1]).strip()
    assert north_face in frame  # partner's card is public
    assert east_face not in frame  # opponent's card is face-down
    # Rules are untouched: legal moves see the real trick.
    unmasked = replace(state, variants=RuleVariants())
    assert legal_cards(state, Seat.WEST) == legal_cards(unmasked, Seat.WEST)


def test_revealed_once_the_first_trick_is_won() -> None:
    s = _play_state()
    first = tuple(TrickCard(seat, s.hand_of(seat)[0]) for seat in Seat)
    after = replace(s, completed_tricks=(first,), current_trick=first)
    assert masked_seats(after) == frozenset()


def test_patch_draws_a_back_for_a_masked_seat(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(TERMINAL, "_size_cache", (120, 40))
    monkeypatch.setattr(R, "_last_render_key", None)
    s = _play_state()
    card = s.hand_of(Seat.WEST)[0]
    state = replace(s, current_trick=(TrickCard(Seat.WEST, card),))
    R.render(state)
    buf = io.StringIO()
    old, sys.stdout = sys.stdout, buf
    try:
        R.patch_trick_card(state, Seat.WEST, card)
    finally:
        sys.stdout = old
    face = _plain(_get_card_face(card, layout=R._last_mat_geometry.fit.layout)[1]).strip()
    assert face not in _plain(buf.getvalue())
