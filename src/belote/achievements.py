"""3.0.0: lightweight achievement registry for classic Belote.

Achievements are defined statically here, evaluated against the running
``Statistics`` object after each round/game, and persisted via the existing
``stats.save_stats()`` path. BelAtro has its own unlock system in
``progression/save.py``; this module is for the classic mode only.
"""

from __future__ import annotations

from dataclasses import dataclass

from .stats import Statistics


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    description: str


# Catalog. New achievements: add a row here AND a check in
# `evaluate_round` / `evaluate_game`. IDs are stable strings — never rename.
ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement(
        "first_capot",
        "Le Grand Chelem",
        "Score your first Capot.",
    ),
    Achievement(
        "capot_x3",
        "Triple Coup",
        "Score 3 Capots in a single session.",
    ),
    Achievement(
        "capot_streak_2",
        "Vague de Capots",
        "Capot two rounds in a row.",
    ),
    Achievement(
        "high_round_300",
        "Cartes Pleines",
        "Score 300+ points in a single round (declarations + Capot).",
    ),
    Achievement(
        "win_hard",
        "Le Maître",
        "Win a game on Hard difficulty.",
    ),
    Achievement(
        "ten_games_played",
        "Habitué",
        "Play 10 games.",
    ),
)


def evaluate_round(stats: Statistics, *, points_scored: int, was_capot: bool) -> list[Achievement]:
    """Check post-round triggers; return list of newly unlocked achievements.

    Mutates ``stats.achievements`` to record unlocks.
    """
    newly: list[Achievement] = []

    def _try(aid: str) -> None:
        if stats.unlock_achievement(aid):
            for a in ACHIEVEMENTS:
                if a.id == aid:
                    newly.append(a)
                    break

    if was_capot:
        if stats.capots_achieved == 1:
            _try("first_capot")
        if stats.capots_achieved >= 3:
            _try("capot_x3")
        if stats.current_capot_streak >= 2:
            _try("capot_streak_2")

    if points_scored >= 300:
        _try("high_round_300")

    return newly


def evaluate_game(
    stats: Statistics, *, won: bool, difficulty: str
) -> list[Achievement]:
    newly: list[Achievement] = []

    def _try(aid: str) -> None:
        if stats.unlock_achievement(aid):
            for a in ACHIEVEMENTS:
                if a.id == aid:
                    newly.append(a)
                    break

    if won and difficulty == "hard":
        _try("win_hard")
    if stats.games_played >= 10:
        _try("ten_games_played")

    return newly
