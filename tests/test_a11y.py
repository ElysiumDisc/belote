"""3.0.1 a11y boss-aware-pts tests.

The pre-3.0.1 a11y trick-winner announcement used raw `card_points()` and
ignored boss zero-rank flags. The screen-reader heard a different number
than the HUD eventually displayed. This file pins that we now share the
canonical `scoring.trick_card_points()` helper.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr

from belote import a11y
from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard
from belote.scoring import trick_card_points


def _trump_jack_trick() -> tuple[TrickCard, ...]:
    """Trump=hearts; Jack of hearts (=20) + 9 (=14) + 7,8 (=0)."""
    return (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.NINE)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.EIGHT)),
    )


def test_trick_card_points_baseline_no_flags() -> None:
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
    )
    assert trick_card_points(state, _trump_jack_trick()) == 34  # J(20)+9(14)


def test_trick_card_points_jacks_zero_zeroes_jack() -> None:
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
        boss_modifiers=BossModifiers(jacks_zero=True),
    )
    assert trick_card_points(state, _trump_jack_trick()) == 14  # only 9


def test_trick_card_points_kings_zero_zeroes_king() -> None:
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.KING)),  # trump K = 4
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.TEN)),    # trump 10 = 10
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.EIGHT)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
        boss_modifiers=BossModifiers(kings_zero=True),
    )
    assert trick_card_points(state, trick) == 10


def test_trick_card_points_aces_zero_zeroes_ace() -> None:
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),  # non-trump A = 11
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
        boss_modifiers=BossModifiers(aces_zero=True),
    )
    assert trick_card_points(state, trick) == 0


def test_trick_card_points_ban_clubs_zeroes_club_led_trick() -> None:
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.ACE)),
        TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.TEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.JACK)),  # trump
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
        boss_modifiers=BossModifiers(ban_clubs=True),
    )
    assert trick_card_points(state, trick) == 0


def test_trick_card_points_empty_trick() -> None:
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        phase=Phase.PLAYING,
    )
    assert trick_card_points(state, ()) == 0


# ── End-to-end: a11y stderr line uses the boss-aware total ────────────────


def test_a11y_announce_trick_won_uses_provided_pts(monkeypatch) -> None:
    """speak() emits one line to stderr only when BELOTE_A11Y is enabled.
    `announce_trick_won(seat, pts)` is the wrapper — verify it uses pts
    verbatim (the gameflow caller now passes a boss-aware total)."""
    monkeypatch.setenv("BELOTE_A11Y", "1")
    a11y._refresh_enabled_from_env()
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            a11y.announce_trick_won(Seat.SOUTH, 14)
        out = buf.getvalue()
        assert "south" in out.lower()
        assert "14" in out
    finally:
        a11y._refresh_enabled_from_env()


def test_a11y_disabled_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("BELOTE_A11Y", raising=False)
    a11y._refresh_enabled_from_env()
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            a11y.announce_trick_won(Seat.SOUTH, 99)
        assert buf.getvalue() == ""
    finally:
        a11y._refresh_enabled_from_env()
