"""3.0.0 replay analyzer tests."""

from __future__ import annotations

from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard
from belote.replay import DecisionReport, analyze_round, summarize


def test_summarize_empty_returns_no_decisions() -> None:
    assert "No decisions" in summarize([])


def test_summarize_format() -> None:
    a = DecisionReport(1, Card(Suit.HEARTS, Rank.ACE), Card(Suit.HEARTS, Rank.ACE), True)
    b = DecisionReport(2, Card(Suit.SPADES, Rank.SEVEN), Card(Suit.SPADES, Rank.JACK), False)
    out = summarize([a, b])
    assert "1/2" in out
    assert "50" in out


def test_analyze_round_skips_non_south_turns() -> None:
    """If the state's turn isn't South, the decision is ignored."""
    state = GameState(
        hands=((Card(Suit.HEARTS, Rank.ACE),), (), (), ()),
        trump=Suit.SPADES,
        turn=Seat.EAST,  # not south
        phase=Phase.PLAYING,
        current_trick=(TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),),
    )
    out = analyze_round([(state, Card(Suit.HEARTS, Rank.ACE))])
    assert out == []


def test_analyze_round_returns_one_report_per_south_decision() -> None:
    """A simple state where South has only one card must produce one report
    where chosen == suggested == that single card."""
    only = Card(Suit.HEARTS, Rank.ACE)
    state = GameState(
        hands=((only,), (), (), ()),
        trump=Suit.SPADES,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    out = analyze_round([(state, only)])
    assert len(out) == 1
    assert out[0].chosen == only
    assert out[0].matched is True
