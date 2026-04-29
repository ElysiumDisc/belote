from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Game rules
    TARGET_SCORE: int = 1000
    LAST_TRICK_BONUS: int = 10
    BELOTE_POINTS: int = 20
    REBELOTE_POINTS: int = 40
    CAPOT_BASE: int = 250
    TOTAL_POINTS: int = 152

    # Timing (ai_move_delay, trick_result_pause, round_result_pause)
    _SPEED_TIMINGS: tuple[tuple[str, tuple[float, float, float]], ...] = (
        ("slow",    (1.5, 2.0, 4.0)),
        ("normal",  (0.7, 1.2, 2.5)),
        ("fast",    (0.25, 0.4, 1.0)),
        ("instant", (0.0, 0.0, 0.5)),
    )

    @property
    def SPEED_TIMINGS(self) -> dict[str, tuple[float, float, float]]:  # noqa: N802
        return dict(self._SPEED_TIMINGS)

    # UI Dimensions
    CARD_W: int = 9
    CARD_H: int = 7
    CARD_GAP: int = 1
    MIN_TERM_W: int = 90
    MIN_TERM_H: int = 32
    THEME_NAME: str = "classic_green"

    @property
    def stats_path(self) -> Path:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            base = Path(xdg_data) / "belote"
        else:
            base = Path.home() / ".local" / "share" / "belote"

        return base / "stats.json"

    def ensure_stats_dir(self) -> None:
        """Create stats directory if it doesn't exist."""
        path = self.stats_path.parent
        import contextlib
        with contextlib.suppress(OSError):
            path.mkdir(parents=True, exist_ok=True)

GLOBAL_CONFIG = Config()
