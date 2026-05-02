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
