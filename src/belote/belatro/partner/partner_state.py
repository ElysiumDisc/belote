from __future__ import annotations

from dataclasses import dataclass, field

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
        if self.trust.ai_degraded:
            return "easy"
        return "medium"

    def equip_joker(self, joker: Joker) -> bool:
        if len(self.jokers) < self.joker_slots:
            self.jokers.append(joker)
            return True
        return False
