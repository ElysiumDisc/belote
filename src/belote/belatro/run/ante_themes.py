"""Phase 3.1 — Ante themes (Café, Tournoi).

A theme is rolled at the start of each ante (blind_index == 0) and applied
across all three blinds of that ante. Themes layer additive effects on top of
the existing ante / boss / joker stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class AnteTheme:
    """Base class for ante themes. Subclasses set id/name/description as class attrs."""

    id: str = ""
    name: str = ""
    description: str = ""

    def on_ante_start(self, run: BelAtroRun) -> None:
        """Hook fired once when this theme is rolled at blind 0."""

    def target_multiplier(self, blind_index: int) -> float:
        """Per-blind multiplier on the target score. Default 1.0 (no change)."""
        return 1.0

    def on_blind_won(self, run: BelAtroRun, blind_index: int, blind_payout: int) -> None:
        """Hook fired after a blind is won under this theme.

        `blind_payout` is the net money awarded for the round (all sources:
        base payout, L'Avocat doubling, bonus money, Le Puriste, L'Aristocrate).
        Themes that want "X% of round payout" must derive it from this value.
        """


class CafeAnte(AnteTheme):
    """+25% chips on blind 0; +1 trust on blind 1 win; gentler boss on blind 2.

    The "gentler boss" effect is implemented via a soft target reduction (5%)
    on blind 2 — keeps the implementation simple without needing per-boss
    overrides.
    """

    id = "cafe"
    name = "Le Café"
    description = (
        "Le Café — petit-blind: +25 chips bonus. "
        "Big-blind: +1 trust on win. "
        "Boss-blind: target 5% softer."
    )

    def on_ante_start(self, run: BelAtroRun) -> None:
        run.permanent_chips += 25  # +25 chips one-shot at theme roll

    def target_multiplier(self, blind_index: int) -> float:
        return 0.95 if blind_index == 2 else 1.0

    def on_blind_won(self, run: BelAtroRun, blind_index: int, blind_payout: int) -> None:
        if blind_index == 1:
            run.partner.trust.blind_beaten()


class TournoiAnte(AnteTheme):
    """+50% money on each blind win; coinche/surcoinche always available."""

    id = "tournoi"
    name = "Le Tournoi"
    description = (
        "Le Tournoi — every win pays 50% extra money. Coinche always offered."
    )

    def on_ante_start(self, run: BelAtroRun) -> None:
        run.card_enhancements["always_offer_coinche"] = True

    def on_blind_won(self, run: BelAtroRun, blind_index: int, blind_payout: int) -> None:
        # True 50% of the round's actual payout (all sources summed).
        # `blind_payout` is computed by the caller from the economy delta.
        run.economy.add_money(max(1, blind_payout // 2))


ALL_ANTE_THEMES: list[type[AnteTheme]] = [CafeAnte, TournoiAnte]
THEME_BY_ID: dict[str, type[AnteTheme]] = {t().id: t for t in ALL_ANTE_THEMES}


def roll_theme(rng_value: float) -> AnteTheme | None:
    """Pick a theme based on `rng_value` ∈ [0, 1) — 30% chance of any theme.

    Caller passes the random value so the run-driver controls the RNG seed.
    """
    if rng_value < 0.15:
        return CafeAnte()
    if rng_value < 0.30:
        return TournoiAnte()
    return None
