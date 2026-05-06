from __future__ import annotations

from dataclasses import dataclass, field

from belote.game import Seat

from ..items.base import Joker
from .personality import LeCourageux, PartnerPersonality
from .trust import TrustTrack


@dataclass
class PartnerState:
    """Wraps the AI partner's status, trust, and personality."""

    trust: TrustTrack = field(default_factory=TrustTrack)
    personality: PartnerPersonality = field(default_factory=LeCourageux)
    jokers: list[Joker] = field(default_factory=list)
    joker_slots: int = 2

    def difficulty_for(self, seat: object) -> str:
        # Only the partner (NORTH) is shaped by trust. Opponent seats keep
        # the standard medium AI; passing them in returns the baseline.
        if seat is not Seat.NORTH:
            return "medium"
        if self.trust.ai_degraded:
            return "easy"
        # tier 3+ (trust value ≥ 7) unlocks hard partner play, mirroring the
        # "strong"/"elite" buckets that partner_jokers/* already scale on.
        if self.trust.tier >= 3:
            return "hard"
        return "medium"

    def equip_joker(self, joker: Joker) -> bool:
        if len(self.jokers) < self.joker_slots:
            self.jokers.append(joker)
            return True
        return False
