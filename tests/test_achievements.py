"""3.0.0 achievement registry tests."""

from __future__ import annotations

from belote.achievements import ACHIEVEMENTS, evaluate_game, evaluate_round
from belote.stats import Statistics


def test_first_capot_unlocks_on_first_capot() -> None:
    stats = Statistics(capots_achieved=1, current_capot_streak=1)
    new = evaluate_round(stats, points_scored=252, was_capot=True)
    ids = {a.id for a in new}
    assert "first_capot" in ids
    # Repeat: already unlocked, shouldn't re-trigger.
    again = evaluate_round(stats, points_scored=252, was_capot=True)
    assert "first_capot" not in {a.id for a in again}


def test_capot_streak_unlocks_at_two_consecutive() -> None:
    stats = Statistics(capots_achieved=2, current_capot_streak=2)
    new = evaluate_round(stats, points_scored=252, was_capot=True)
    assert "capot_streak_2" in {a.id for a in new}


def test_high_round_300_unlocks() -> None:
    stats = Statistics()
    new = evaluate_round(stats, points_scored=305, was_capot=False)
    assert "high_round_300" in {a.id for a in new}


def test_win_hard_unlocks_on_hard_win() -> None:
    stats = Statistics()
    new = evaluate_game(stats, won=True, difficulty="hard")
    assert "win_hard" in {a.id for a in new}


def test_win_hard_does_not_unlock_on_easy() -> None:
    stats = Statistics()
    new = evaluate_game(stats, won=True, difficulty="easy")
    assert "win_hard" not in {a.id for a in new}


def test_ten_games_played_unlocks_at_ten() -> None:
    stats = Statistics(games_played=10)
    new = evaluate_game(stats, won=False, difficulty="medium")
    assert "ten_games_played" in {a.id for a in new}


def test_unlock_achievement_idempotent() -> None:
    stats = Statistics()
    assert stats.unlock_achievement("test_id") is True
    assert stats.unlock_achievement("test_id") is False
    assert stats.achievements.count("test_id") == 1


def test_all_achievements_have_distinct_ids() -> None:
    ids = [a.id for a in ACHIEVEMENTS]
    assert len(ids) == len(set(ids))
