"""3.0.0 replay analyzer tests."""

from __future__ import annotations

import random

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


def test_analyze_round_deterministic_under_seeded_rng() -> None:
    """3.3.2: `analyze_round` must thread the caller's seeded RNG into the
    Hard AI so the same decisions reproduce. Pre-3.3.2 the constructor
    fell back to an unseeded `random.Random()`, so the SA fallback path
    (`_hard_play` → `_easy_play` → `rng.choice(legal)`) returned a
    different suggested card between runs on the same data.
    """
    # Sans Atout state with multiple legal cards. `_hard_play` falls through
    # to `_easy_play` under SA (trump is None) → `self._rng.choice(legal)`
    # is the only thing picking the suggested card; an unseeded RNG makes
    # the report non-reproducible.
    hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.JACK),
    )
    state = GameState(
        hands=(hand, (), (), ()),
        trump=None,
        contract="sans_atout",
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    chosen = hand[0]

    reports_a = analyze_round([(state, chosen)], rng=random.Random(42))
    reports_b = analyze_round([(state, chosen)], rng=random.Random(42))
    reports_c = analyze_round([(state, chosen)], rng=random.Random(42))
    assert reports_a == reports_b == reports_c

    # Different seed may or may not pick the same card — but each seed
    # must be self-consistent.
    reports_d = analyze_round([(state, chosen)], rng=random.Random(7))
    reports_e = analyze_round([(state, chosen)], rng=random.Random(7))
    assert reports_d == reports_e
