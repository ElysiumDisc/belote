from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from ..engine.event_bus import (
        BeloteAnnouncedEvent,
        BidMadeEvent,
        DeclarationScoredEvent,
        RoundEndEvent,
        TrickWonEvent,
    )


class Rarity(str, Enum):
    """Item rarity for shop weighting and unlock-gating."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    LEGENDARY = "legendary"


@dataclass(frozen=True)
class JokerResult:
    add_chips: int = 0
    add_mult: float = 0.0
    times_mult: float = 0.0
    add_money: int = 0


class Joker(ABC):
    id: str
    name: str
    description: str
    cost: int = 7
    rarity: Rarity = Rarity.COMMON
    fusable: bool = True
    is_partner_joker: bool = False
    is_corrupted: bool = False

    def on_trick_won(self, event: TrickWonEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_belote(self, event: BeloteAnnouncedEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_declaration(self, event: DeclarationScoredEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_round_start(self, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_round_end(self, event: RoundEndEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_bid(self, event: BidMadeEvent, state: dict[str, Any]) -> JokerResult | None:
        return None

    def on_purchase(self, run: BelAtroRun) -> None:  # noqa: B027
        """Called once when the joker is bought. Apply permanent run-level effects here."""


class Planet(ABC):
    id: str
    name: str
    contract_id: str  # which contract this levels up
    level: int = 0
    cost: int = 4
    rarity: Rarity = Rarity.COMMON
    suit_symbol: str = "?"
    ascii_art: tuple[str, str, str] = (
        "              ",
        "   (  ?  ?  ) ",
        "   Planet  ♪  ",
    )
    shop_lines: tuple[str, str] = ("              ", "              ")

    @abstractmethod
    def level_up_reward(self) -> dict[str, Any]:
        """Returns a dict of stat bumps to apply to contract."""
        ...

    def use(self, run: BelAtroRun) -> None:
        """Apply this planet's level-up reward to the run's contract_levels."""
        reward = self.level_up_reward()
        existing = run.contract_levels.get(self.contract_id, {})
        merged: dict[str, Any] = {}
        for key, val in {**existing, **reward}.items():
            if key in existing and key in reward:
                merged[key] = existing[key] + reward[key]
            else:
                merged[key] = val
        run.contract_levels[self.contract_id] = merged


class Tarot(ABC):
    id: str
    name: str
    description: str
    cost: int = 4
    rarity: Rarity = Rarity.COMMON

    @abstractmethod
    def use(self, run: BelAtroRun, context: object) -> None:
        """Apply the one-shot effect."""
        ...


class Voucher(ABC):
    id: str
    name: str
    description: str
    cost: int = 10
    rarity: Rarity = Rarity.COMMON
    purchased: bool = False

    @abstractmethod
    def apply(self, run: BelAtroRun) -> None:
        """Apply permanent effect to the run."""
        ...


# ── Phase 3.2: Joker fusion (Endless mode) ────────────────────────────────


_RARITY_LADDER = (Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.LEGENDARY)


class FusionError(Exception):
    """Raised when two jokers can't be fused (legendary, marked unfusable, etc.)."""


def fuse_jokers(a: Joker, b: Joker) -> Joker:
    """Combine two jokers into a single upgraded one.

    Rules:
    - Both must have `fusable=True`.
    - Neither may be Legendary (no compounding endgame ramps).
    - The result inherits the *first* joker's identity (id/name/desc/hooks),
      with `fusable=False` so it can't be re-fused, and rarity bumped one
      tier (clamped at RARE — never auto-promotes to LEGENDARY).
    """
    if not getattr(a, "fusable", True) or not getattr(b, "fusable", True):
        raise FusionError("One of the jokers is marked fusable=False")
    if a.rarity == Rarity.LEGENDARY or b.rarity == Rarity.LEGENDARY:
        raise FusionError("Legendary jokers cannot be fused")

    fused = type(a)()
    # Bump rarity one tier (clamp at RARE).
    base_idx = max(_RARITY_LADDER.index(a.rarity), _RARITY_LADDER.index(b.rarity))
    new_idx = min(base_idx + 1, _RARITY_LADDER.index(Rarity.RARE))
    fused.rarity = _RARITY_LADDER[new_idx]
    fused.fusable = False  # one-time fusion only
    # Stamp a marker so callers can identify fused jokers
    fused.name = f"{a.name} + {b.name}"
    return fused
