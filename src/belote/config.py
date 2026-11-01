from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import data_dir


@dataclass(frozen=True)
class Config:
    # Game rules
    TARGET_SCORE: int = 1000
    LAST_TRICK_BONUS: int = 10
    # Official French Belote: holding the King AND Queen of trump (announced
    # "Belote" on the first played, "Rebelote" on the second) is worth 20
    # points TOTAL — not 20 each. BELOTE_POINTS is the provisional credit once
    # the first card is announced; REBELOTE_POINTS is the final value once the
    # pair is complete. Both are 20 so the completed pair scores the official 20.
    BELOTE_POINTS: int = 20
    REBELOTE_POINTS: int = 20
    CAPOT_BASE: int = 252
    # Capot bases for special contracts. Standard FFB practice scales the
    # Capot reward to the contract's total card points: Capot pays the deck
    # total + 100 (the standard "Capot bonus"). For SA: 120 + 100 = 220.
    # For TA: 248 + 100 = 348. Pre-3.0.0 the engine awarded a flat 252 for
    # all contracts, which over-paid SA Capots (252 vs. 220) and under-paid
    # TA Capots (252 vs. 348).
    CAPOT_BASE_SANS_ATOUT: int = 220
    CAPOT_BASE_TOUT_ATOUT: int = 348
    TOTAL_POINTS: int = 152
    # Sum over the 32-card deck under each contract. TA scores every card on
    # the trump scale (J=20, 9=14, A=11, 10=10, K=4, Q=3, 7/8=0 → 62/suit ×4).
    # SA scores every card on the non-trump scale (A=11, 10=10, K=4, Q=3, J=2,
    # 9/8/7=0 → 30/suit ×4).
    TOTAL_POINTS_TOUT_ATOUT: int = 248
    TOTAL_POINTS_SANS_ATOUT: int = 120

    # Timing (ai_move_delay, trick_result_pause, round_result_pause)
    _SPEED_TIMINGS: tuple[tuple[str, tuple[float, float, float]], ...] = (
        ("slow", (1.5, 2.0, 4.0)),
        ("normal", (0.7, 1.2, 2.5)),
        ("fast", (0.25, 0.4, 1.0)),
        ("instant", (0.0, 0.0, 0.5)),
    )

    @property
    def SPEED_TIMINGS(self) -> dict[str, tuple[float, float, float]]:  # noqa: N802
        return dict(self._SPEED_TIMINGS)

    # UI dimensions live in `belote.ui.layout` (choose_layout / MIN_COLS /
    # MIN_ROWS); the theme selection lives in `belote.themes`.

    @property
    def stats_path(self) -> Path:
        # Shared with the BelAtro profile / run history / ghosts via
        # belote.paths so every data file lives side by side.
        base = data_dir()
        # Don't mkdir here — every reader/writer that actually persists
        # (stats.save_stats, save.SaveManager.save_profile) ensures the
        # directory exists at write time. Side-effecting on every property
        # access used to syscall on every render path.
        return base / "stats.json"


GLOBAL_CONFIG = Config()
