from __future__ import annotations

from dataclasses import dataclass

VOID_INFO_THRESHOLD = 3
DUO_CONTRACT_THRESHOLD = 5
DOUBLE_TRIGGER_THRESHOLD = 7
AUTO_CAPOT_THRESHOLD = 9
AI_DEGRADE_THRESHOLD = 2


@dataclass
class TrustTrack:
    """Tracks the trust relationship between the player and their AI partner.

    Value ranges 0–10. Higher = more cooperative partner behaviours unlock.
    """

    value: int = 5
    auto_capot_used: bool = False

    # ── Positive events ────────────────────────────────────────────────────

    def blind_beaten(self) -> None:
        self.value = min(10, self.value + 1)

    def big_margin_win(self) -> None:
        self.value = min(10, self.value + 2)

    def capot_together(self) -> None:
        self.value = min(10, self.value + 3)

    # ── Negative events ────────────────────────────────────────────────────

    def blind_failed(self) -> None:
        self.value = max(0, self.value - 1)

    def chute(self) -> None:
        self.value = max(0, self.value - 2)

    # ── Threshold properties ───────────────────────────────────────────────

    @property
    def shares_void_info(self) -> bool:
        """Partner tells player which suits they are void in."""
        return self.value >= VOID_INFO_THRESHOLD

    @property
    def duo_contracts_available(self) -> bool:
        """Partner will consider bidding on Tout Atout or Sans Atout."""
        return self.value >= DUO_CONTRACT_THRESHOLD

    @property
    def partner_jokers_double(self) -> bool:
        """Partner joker effects count double."""
        return self.value >= DOUBLE_TRIGGER_THRESHOLD

    @property
    def auto_capot_available(self) -> bool:
        """Partner will attempt a capot if conditions are right."""
        return self.value >= AUTO_CAPOT_THRESHOLD and not self.auto_capot_used

    @property
    def ai_degraded(self) -> bool:
        """Partner plays at Easy difficulty due to low trust."""
        return self.value <= AI_DEGRADE_THRESHOLD

    def partner_passes_all(self) -> None:
        """Called when partner deliberately passes every bid (full breakdown)."""
        self.value = 0

    @property
    def tier(self) -> int:
        """Five-tier bucketing for partner-joker effect scaling.

        Scaling is implemented as N *extra* applications of the joker's
        JokerResult on top of the baseline one (see
        ``ScoreAccumulator._fire_jokers``; ``tier_extras = (0, 0, 1, 1, 2)``):

        0 (degraded, value 0–2) — baseline only (no bonus, no penalty)
        1 (base,     value 3–4) — baseline only
        2 (boost,    value 5–6) — +1 apply  (≈ ×2 effect)
        3 (strong,   value 7–8) — +1 apply  (≈ ×2 effect)
        4 (elite,    value 9–10) — +2 applies (≈ ×3 effect)

        Used by partner_jokers/* to scale their JokerResult payloads. The
        legacy `partner_jokers_double` flag (value≥7) still exists for backward
        compatibility but tier is the new path.
        """
        if self.value <= 2:
            return 0
        if self.value <= 4:
            return 1
        if self.value <= 6:
            return 2
        if self.value <= 8:
            return 3
        return 4

    def mood(self) -> str:
        """Single-word descriptor for HUD display: degraded/sulking/neutral/eager/elated."""
        return ["degraded", "sulking", "neutral", "eager", "elated"][self.tier]
