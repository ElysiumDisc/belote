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


def test_first_capot_unlocks_when_count_already_above_one() -> None:
    """`== 1` missed the unlock for stats files that predate achievements."""
    stats = Statistics(capots_achieved=4, current_capot_streak=1)
    new = evaluate_round(stats, points_scored=252, was_capot=True)
    assert "first_capot" in {a.id for a in new}


def test_capot_x3_uses_session_count_not_lifetime() -> None:
    """"Triple Coup — 3 Capots in a single session": lifetime capots from
    earlier sessions must not unlock it."""
    stats = Statistics(capots_achieved=10, current_capot_streak=1)
    new = evaluate_round(stats, points_scored=252, was_capot=True, session_capots=1)
    assert "capot_x3" not in {a.id for a in new}
    new = evaluate_round(stats, points_scored=252, was_capot=True, session_capots=3)
    assert "capot_x3" in {a.id for a in new}


def _breakdown(taker_team: int, *, is_capot: bool, is_failed: bool) -> object:
    from belote.scoring import ScoringBreakdown

    return ScoringBreakdown(
        taker_team=taker_team,
        table_taker_pts=0,
        table_defender_pts=0,
        credit_taker_pts=0,
        credit_defender_pts=0,
        last_trick_team=None,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=0,
        defender_total=0,
        is_capot=is_capot,
        is_failed=is_failed,
    )


def test_player_capot_flag_only_for_ns() -> None:
    """`is_capot` is set for either team's capot; only NS's counts for the
    player's stats/achievements."""
    from belote.gameflow import _is_player_capot

    # NS took it and made it (NS capot).
    assert _is_player_capot(_breakdown(0, is_capot=True, is_failed=False))  # type: ignore[arg-type]
    # EW took it and made it (EW capot) — the bug: this counted for the player.
    assert not _is_player_capot(_breakdown(1, is_capot=True, is_failed=False))  # type: ignore[arg-type]
    # EW took it, NS capoted them (failed contract) → player's capot.
    assert _is_player_capot(_breakdown(1, is_capot=True, is_failed=True))  # type: ignore[arg-type]
    # NS took it, EW capoted them → not the player's.
    assert not _is_player_capot(_breakdown(0, is_capot=True, is_failed=True))  # type: ignore[arg-type]
    # No capot at all.
    assert not _is_player_capot(_breakdown(0, is_capot=False, is_failed=False))  # type: ignore[arg-type]


def test_ew_capot_round_does_not_count_as_player_capot() -> None:
    """End-to-end through the real scorer: EW takes and wins all 8 tricks."""
    import random
    from dataclasses import replace

    from belote.deck import Card, Rank, Suit
    from belote.game import Phase, Seat, TrickCard, new_game, start_round
    from belote.gameflow import _is_player_capot
    from belote.scoring import score_round

    # East (taker) leads a spade — trump — every trick; nobody else holds one.
    trumps = [Card(Suit.SPADES, r) for r in Rank]
    others = [Card(s, r) for s in (Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS) for r in Rank]
    tricks = tuple(
        (
            TrickCard(Seat.EAST, trumps[i]),
            TrickCard(Seat.NORTH, others[i * 3]),
            TrickCard(Seat.WEST, others[i * 3 + 1]),
            TrickCard(Seat.SOUTH, others[i * 3 + 2]),
        )
        for i in range(8)
    )
    st = replace(
        start_round(new_game(), random.Random(0)),
        phase=Phase.SCORING,
        trump=Suit.SPADES,
        taker=Seat.EAST,
        hands=((), (), (), ()),
        current_trick=(),
        completed_tricks=tricks,
    )
    bd = score_round(st)
    assert bd.is_capot and bd.taker_team == 1 and not bd.is_failed
    assert not _is_player_capot(bd)
