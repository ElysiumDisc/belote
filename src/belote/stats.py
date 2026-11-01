from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING

from .config import GLOBAL_CONFIG

if TYPE_CHECKING:
    from .achievements import Achievement

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
        # Handle migration of old stats: unknown keys are dropped, missing
        # keys keep their defaults, and wrong-typed values (hand-edited or
        # corrupted file, e.g. `"most_used_trump": null`) fall back to the
        # default per field instead of crashing the first update.
        base = cls()
        for f in fields(cls):
            if f.name in data:
                setattr(base, f.name, _conform(getattr(base, f.name), data[f.name]))
        return base


def _conform(template: object, value: object) -> object:
    """Return `value` coerced to the shape of `template` (a default field
    value), falling back to `template` wherever the types don't match."""
    if isinstance(template, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
        return value if ok else template
    if isinstance(template, list):
        # Only list[str] (achievement IDs) exists today.
        if not isinstance(value, list):
            return template
        return [v for v in value if isinstance(v, str)]
    if isinstance(template, dict):
        if not isinstance(value, dict):
            return template
        out = dict(template)
        # Keys absent from the defaults (e.g. a future difficulty) are kept
        # if they match the shape of the default entries.
        sample = next(iter(template.values()), None)
        for k, v in value.items():
            ref = template.get(k, sample)
            if isinstance(k, str) and ref is not None:
                out[k] = _conform(ref, v)
        return out
    return template


def _cosmetic_unlocks(stats: Statistics) -> list[Achievement]:
    """Card backs / table frames whose milestone was just met, shaped as
    achievements so the callers' existing toast loop announces them (4.11.0).
    Evaluated after the achievements, which the Gilded frame counts. Never
    lets a cosmetics problem break the stats update."""
    from .cosmetics import unlock_toasts

    try:
        return unlock_toasts(stats)
    except Exception as e:
        _log.info("cosmetic unlock check failed: %s", e)
        return []


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
            raw = self.stats_file.read_bytes()
        except OSError:
            # Unreadable (permissions, I/O error): use defaults but leave the
            # file alone — it may be perfectly fine.
            self._stats_cache = Statistics()
            return self._stats_cache
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            self._stats_cache = Statistics.from_dict(data)
        else:
            # Unparseable or not an object (`[]`, `null`, truncated write):
            # keep a copy for the player instead of letting the next save
            # silently overwrite their history.
            self._quarantine_corrupt_file()
            self._stats_cache = Statistics()
        return self._stats_cache

    def _quarantine_corrupt_file(self) -> None:
        backup = self.stats_file.with_name(self.stats_file.name + ".bak")
        try:
            self.stats_file.replace(backup)
            # info, not warning: with no handler configured a warning goes to
            # stderr and would scribble over the raw-mode game screen.
            _log.info("Corrupt stats file moved to %s", backup)
        except OSError as e:
            _log.warning("Corrupt stats file %s could not be moved aside: %s", self.stats_file, e)

    def save_stats(self, stats: Statistics) -> None:
        # Atomic write (sibling tmp file + fsync + os.replace): writing in
        # place truncated stats.json first, so a crash or full disk mid-write
        # lost the player's whole history.
        tmp_path: Path | None = None
        try:
            directory = self.stats_file.parent
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(directory),
                prefix=".stats-",
                suffix=".json.tmp",
                delete=False,
            ) as tf:
                tmp_path = Path(tf.name)
                json.dump(stats.to_dict(), tf, indent=2)
                tf.flush()
                os.fsync(tf.fileno())
            tmp_path.replace(self.stats_file)
        except OSError as e:
            _log.warning("Failed to save stats to %s: %s", self.stats_file, e)
            if tmp_path is not None:
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    def flush_stats(self) -> None:
        """Write cached stats to disk."""
        if self._stats_cache is not None:
            self.save_stats(self._stats_cache)

    def update_stats_round(
        self, is_capot: bool, points_scored: int, trump_symbol: str | None = None
    ) -> list[Achievement]:
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

        unlocked = evaluate_round(
            stats,
            points_scored=points_scored,
            was_capot=is_capot,
            session_capots=self._session_stats.capots,
        )
        unlocked += _cosmetic_unlocks(stats)

        # Persist after every round so a mid-game crash doesn't lose
        # round-level stats or freshly-unlocked achievements.
        self.flush_stats()
        return unlocked

    def update_stats_game(self, won: bool, num_rounds: int, difficulty: str) -> list[Achievement]:
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

        unlocked = evaluate_game(stats, won=won, difficulty=difficulty)
        unlocked += _cosmetic_unlocks(stats)

        self.flush_stats()
        return unlocked

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


def update_stats_round(
    is_capot: bool, points_scored: int, trump_symbol: str | None = None
) -> list[Achievement]:
    """Record a finished round; returns the achievements it newly unlocked."""
    return _MANAGER.update_stats_round(is_capot, points_scored, trump_symbol)


def update_stats_game(won: bool, num_rounds: int, difficulty: str) -> list[Achievement]:
    """Record a finished game; returns the achievements it newly unlocked."""
    return _MANAGER.update_stats_game(won, num_rounds, difficulty)


def get_session_stats() -> SessionStats:
    return _MANAGER.get_session_stats()
