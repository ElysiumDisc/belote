from __future__ import annotations

import json
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
    
    # Enhanced stats
    most_used_trump: dict[str, int] = field(default_factory=lambda: {
        "♠": 0, "♥": 0, "♦": 0, "♣": 0
    })
    difficulty_stats: dict[str, dict[str, int]] = field(default_factory=lambda: {
        "easy": {"played": 0, "won": 0},
        "medium": {"played": 0, "won": 0},
        "hard": {"played": 0, "won": 0},
        "mixed": {"played": 0, "won": 0}
    })
    longest_game_rounds: int = 0
    best_round_score: int = 0
    worst_round_score: int = 200 # Higher than max possible (162 + decls)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Statistics:
        # Handle migration of old stats
        base = cls()
        for key, value in data.items():
            if hasattr(base, key):
                setattr(base, key, value)
        return base


@dataclass
class SessionStats:
    games_played: int = 0
    games_won: int = 0
    total_rounds: int = 0
    total_points: int = 0
    capots: int = 0

_STATS_CACHE: Statistics | None = None
_SESSION_STATS: SessionStats = SessionStats()


def load_stats() -> Statistics:
    global _STATS_CACHE
    if _STATS_CACHE is not None:
        return _STATS_CACHE
        
    if not STATS_FILE.exists():
        _STATS_CACHE = Statistics()
        return _STATS_CACHE
    try:
        with open(STATS_FILE, "r") as f:
            _STATS_CACHE = Statistics.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        _STATS_CACHE = Statistics()
    return _STATS_CACHE


def save_stats(stats: Statistics) -> None:
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats.to_dict(), f, indent=2)
    except OSError:
        pass


def flush_stats() -> None:
    """Write cached stats to disk."""
    if _STATS_CACHE is not None:
        save_stats(_STATS_CACHE)


def update_stats_round(is_capot: bool, points_scored: int, trump_symbol: str | None = None) -> None:
    stats = load_stats()
    stats.total_rounds += 1
    stats.total_points_scored += points_scored
    
    # Session stats
    _SESSION_STATS.total_rounds += 1
    _SESSION_STATS.total_points += points_scored

    if is_capot:
        stats.capots_achieved += 1
        stats.current_capot_streak += 1
        stats.max_capot_streak = max(stats.max_capot_streak, stats.current_capot_streak)
        _SESSION_STATS.capots += 1
    else:
        stats.current_capot_streak = 0
        
    if trump_symbol and trump_symbol in stats.most_used_trump:
        stats.most_used_trump[trump_symbol] += 1
        
    stats.best_round_score = max(stats.best_round_score, points_scored)
    if points_scored > 0: # Only count rounds where user actually scored
        stats.worst_round_score = min(stats.worst_round_score, points_scored)


def update_stats_game(won: bool, num_rounds: int, difficulty: str) -> None:
    stats = load_stats()
    stats.games_played += 1
    _SESSION_STATS.games_played += 1
    
    if won:
        stats.games_won += 1
        _SESSION_STATS.games_won += 1
        
    stats.longest_game_rounds = max(stats.longest_game_rounds, num_rounds)
    
    if difficulty in stats.difficulty_stats:
        stats.difficulty_stats[difficulty]["played"] += 1
        if won:
            stats.difficulty_stats[difficulty]["won"] += 1


def get_session_stats() -> SessionStats:
    return _SESSION_STATS
