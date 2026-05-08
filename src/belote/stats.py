from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import GLOBAL_CONFIG

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class Statistics:
    games_played: int = 0
    games_won: int = 0
    total_rounds: int = 0
    total_points_scored: int = 0
    capots_achieved: int = 0
    max_capot_streak: int = 0
    current_capot_streak: int = 0

    # Enhanced stats
    most_used_trump: dict[str, int] = field(
        default_factory=lambda: {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
    )
    difficulty_stats: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "easy": {"played": 0, "won": 0},
            "medium": {"played": 0, "won": 0},
            "hard": {"played": 0, "won": 0},
            "mixed": {"played": 0, "won": 0},
        }
    )
    longest_game_rounds: int = 0
    best_round_score: int = 0
    worst_round_score: int = 999  # Higher than max possible (162 + decls)

    # 3.0.0: Achievement registry — IDs of unlocked achievements. List
    # rather than set for JSON-friendliness; uniqueness enforced on insert.
    achievements: list[str] = field(default_factory=list)

    def unlock_achievement(self, ach_id: str) -> bool:
        """Returns True if newly unlocked; False if already had it."""
        if ach_id in self.achievements:
            return False
        self.achievements.append(ach_id)
        return True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Statistics:
        # Handle migration of old stats
        base = cls()
        for key, value in data.items():
            if hasattr(base, key):
                setattr(base, key, value)
        return base


@dataclass(slots=True)
class SessionStats:
    games_played: int = 0
    games_won: int = 0
    total_rounds: int = 0
    total_points: int = 0
    capots: int = 0


class StatisticsManager:
    def __init__(self, stats_file: Path | None = None):
        self.stats_file = stats_file or GLOBAL_CONFIG.stats_path
        self._stats_cache: Statistics | None = None
        self._session_stats = SessionStats()

    def load_stats(self) -> Statistics:
        if self._stats_cache is not None:
            return self._stats_cache

        if not self.stats_file.exists():
            self._stats_cache = Statistics()
            return self._stats_cache
        try:
            with self.stats_file.open() as f:
                self._stats_cache = Statistics.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            self._stats_cache = Statistics()
        return self._stats_cache

    def save_stats(self, stats: Statistics) -> None:
        try:
            # Ensure directory exists (again, just in case)
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            with self.stats_file.open("w") as f:
                json.dump(stats.to_dict(), f, indent=2)
        except OSError as e:
            _log.warning("Failed to save stats to %s: %s", self.stats_file, e)

    def flush_stats(self) -> None:
        """Write cached stats to disk."""
        if self._stats_cache is not None:
            self.save_stats(self._stats_cache)

    def update_stats_round(
        self, is_capot: bool, points_scored: int, trump_symbol: str | None = None
    ) -> None:
        stats = self.load_stats()
        stats.total_rounds += 1
        stats.total_points_scored += points_scored

        # Session stats
        self._session_stats.total_rounds += 1
        self._session_stats.total_points += points_scored

        if is_capot:
            stats.capots_achieved += 1
            stats.current_capot_streak += 1
            stats.max_capot_streak = max(stats.max_capot_streak, stats.current_capot_streak)
            self._session_stats.capots += 1
        else:
            stats.current_capot_streak = 0

        if trump_symbol and trump_symbol in stats.most_used_trump:
            stats.most_used_trump[trump_symbol] += 1

        stats.best_round_score = max(stats.best_round_score, points_scored)
        stats.worst_round_score = min(stats.worst_round_score, points_scored)

        # 3.0.0: evaluate achievements. Unlocks are recorded on `stats` and
        # the announcement is left to the caller (we don't want stats.py to
        # depend on the UI). Callers can read stats.achievements to detect
        # the new entries.
        from .achievements import evaluate_round
        evaluate_round(stats, points_scored=points_scored, was_capot=is_capot)

    def update_stats_game(self, won: bool, num_rounds: int, difficulty: str) -> None:
        stats = self.load_stats()
        stats.games_played += 1
        self._session_stats.games_played += 1

        if won:
            stats.games_won += 1
            self._session_stats.games_won += 1

        stats.longest_game_rounds = max(stats.longest_game_rounds, num_rounds)

        if difficulty in stats.difficulty_stats:
            stats.difficulty_stats[difficulty]["played"] += 1
            if won:
                stats.difficulty_stats[difficulty]["won"] += 1

        from .achievements import evaluate_game
        evaluate_game(stats, won=won, difficulty=difficulty)

        self.flush_stats()

    def reset_stats(self) -> None:
        self._stats_cache = Statistics()
        self.save_stats(self._stats_cache)

    def get_session_stats(self) -> SessionStats:
        return self._session_stats


# Global instance for backward compatibility (can be replaced with DI later)
_MANAGER = StatisticsManager()


def load_stats() -> Statistics:
    return _MANAGER.load_stats()


def save_stats(stats: Statistics) -> None:
    _MANAGER.save_stats(stats)


def reset_stats() -> None:
    _MANAGER.reset_stats()


def flush_stats() -> None:
    _MANAGER.flush_stats()


def update_stats_round(is_capot: bool, points_scored: int, trump_symbol: str | None = None) -> None:
    _MANAGER.update_stats_round(is_capot, points_scored, trump_symbol)


def update_stats_game(won: bool, num_rounds: int, difficulty: str) -> None:
    _MANAGER.update_stats_game(won, num_rounds, difficulty)


def get_session_stats() -> SessionStats:
    return _MANAGER.get_session_stats()
