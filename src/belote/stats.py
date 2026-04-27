from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

STATS_FILE = Path.home() / ".belote_stats.json"

@dataclass
class Statistics:
    games_played: int = 0
    games_won: int = 0
    total_rounds: int = 0
    total_points_scored: int = 0
    capots_achieved: int = 0
    max_capot_streak: int = 0
    current_capot_streak: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Statistics:
        return cls(**data)


def load_stats() -> Statistics:
    if not STATS_FILE.exists():
        return Statistics()
    try:
        with open(STATS_FILE, "r") as f:
            return Statistics.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return Statistics()


def save_stats(stats: Statistics) -> None:
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats.to_dict(), f, indent=2)
    except OSError:
        pass


def update_stats_round(is_capot: bool, points_scored: int) -> None:
    stats = load_stats()
    stats.total_rounds += 1
    stats.total_points_scored += points_scored
    if is_capot:
        stats.capots_achieved += 1
        stats.current_capot_streak += 1
        stats.max_capot_streak = max(stats.max_capot_streak, stats.current_capot_streak)
    else:
        stats.current_capot_streak = 0
    save_stats(stats)


def update_stats_game(won: bool) -> None:
    stats = load_stats()
    stats.games_played += 1
    if won:
        stats.games_won += 1
    save_stats(stats)
