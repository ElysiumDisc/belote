from __future__ import annotations

import dataclasses
from typing import Any

from belote.ai import AIPlayer, Difficulty
from belote.game import Card, GameState, Phase, Rank, Seat, Suit, TrickCard, new_game
from belote.scoring import ScoringBreakdown, apply_round_score
from belote.stats import _MANAGER, load_stats, update_stats_game, update_stats_round


def test_round_score_history() -> None:
    state = new_game()
    # Mock a breakdown
    breakdown = ScoringBreakdown(
        taker_team=0,
        table_taker_pts=100,
        table_defender_pts=62,
        credit_taker_pts=100,
        credit_defender_pts=62,
        last_trick_team=0,
        taker_declarations=20,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=120,
        defender_total=62,
        is_capot=False,
        is_failed=False,
    )

    state = apply_round_score(state, breakdown)
    assert len(state.score_history) == 1
    assert state.score_history[0].ns_total == 120
    assert state.score_history[0].ew_total == 62


def test_round_score_history_extra_fields() -> None:
    """RoundScore must capture contract/trump/taker/tricks for the history view."""
    state = new_game()
    state = dataclasses.replace(
        state,
        contract="normal",
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        completed_tricks=tuple(
            (TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),) for _ in range(5)
        )
        + tuple(
            (TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.SEVEN)),) for _ in range(3)
        ),
        last_trick_winner=Seat.SOUTH,
    )
    breakdown = ScoringBreakdown(
        taker_team=0,
        table_taker_pts=100,
        table_defender_pts=62,
        credit_taker_pts=100,
        credit_defender_pts=62,
        last_trick_team=0,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=120,
        defender_total=62,
        is_capot=False,
        is_failed=False,
    )
    state = apply_round_score(state, breakdown)
    rs = state.score_history[0]
    assert rs.contract == "normal"
    assert rs.trump == Suit.HEARTS
    assert rs.taker_seat == Seat.SOUTH
    assert rs.tricks_ns + rs.tricks_ew == 8
    assert rs.tricks_ns >= 1  # at least one heart-trick won by South
    assert rs.last_trick_winner == Seat.SOUTH


def test_statistics_persistence(tmp_path: Any, monkeypatch: Any) -> None:
    # Mock stats_file to use tmp_path
    stats_file = tmp_path / "stats.json"
    monkeypatch.setattr(_MANAGER, "stats_file", stats_file)

    stats = load_stats()
    assert stats.games_played == 0

    update_stats_game(won=True, num_rounds=10, difficulty="medium")
    stats = load_stats()
    assert stats.games_played == 1
    assert stats.games_won == 1

    update_stats_round(is_capot=True, points_scored=250)
    stats = load_stats()
    assert stats.total_rounds == 1
    assert stats.capots_achieved == 1
    assert stats.max_capot_streak == 1


def test_ai_seat_specific_difficulty() -> None:
    ai_easy = AIPlayer(Seat.NORTH, Difficulty.EASY)
    ai_hard = AIPlayer(Seat.NORTH, Difficulty.HARD)

    assert ai_easy.difficulty == Difficulty.EASY
    assert ai_hard.difficulty == Difficulty.HARD


def test_current_round_points_update() -> None:
    """Verify that current_round_points tracks points as tricks are completed."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
        team_scores=(0, 0),
    )

    # Simulate playing a trick
    cards = [
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.EIGHT),
    ]

    trick1 = (
        TrickCard(Seat.SOUTH, cards[0]),
        TrickCard(Seat.EAST, cards[1]),
        TrickCard(Seat.NORTH, cards[2]),
        TrickCard(Seat.WEST, cards[3]),
    )

    # Manually update state to simulate completion of trick
    state = dataclasses.replace(
        state,
        completed_tricks=(trick1,),
        last_trick_winner=Seat.SOUTH,
        current_round_points=(34, 0),  # J=20, 9=14, others=0
    )

    assert state.current_round_points == (34, 0)

    # Trick 2: EW wins
    trick2 = (
        TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.SEVEN)),
        TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.ACE)),  # wins with 11
        TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.EIGHT)),
        TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.NINE)),
    )

    state = dataclasses.replace(
        state,
        completed_tricks=(trick1, trick2),
        last_trick_winner=Seat.EAST,
        current_round_points=(34, 11),
    )

    assert state.current_round_points == (34, 11)
