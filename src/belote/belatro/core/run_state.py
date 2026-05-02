from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..items.base import Joker, Voucher
    from ..progression.save import Profile
    from ..run.ante import Ante

from ..partner.partner_state import PartnerState
from .economy import Economy

MAX_JOKER_SLOTS = 5


@dataclass
class BelAtroRun:
    """Top-level mutable state for one complete Belatro run."""

    # ── Progression ────────────────────────────────────────
    ante_number: int = 1  # 1–8
    blind_index: int = 0  # 0=Small, 1=Big, 2=Boss
    run_over: bool = False
    run_won: bool = False
    profile: Profile | None = None

    # ── Collectibles ───────────────────────────────────────
    jokers: list[Joker] = field(default_factory=list)
    vouchers: list[Voucher] = field(default_factory=list)
    joker_slots: int = MAX_JOKER_SLOTS

    # ── Economy ────────────────────────────────────────────
    economy: Economy = field(default_factory=Economy)

    # ── Partner ────────────────────────────────────────────
    partner: PartnerState = field(default_factory=PartnerState)

    # ── Deck ───────────────────────────────────────────────
    deck_id: str = "classique"
    card_enhancements: dict[str, Any] = field(default_factory=dict)  # card_id → Enhancement
    show_north_hand: bool = False  # set True by LeCarnet voucher

    def __post_init__(self) -> None:
        from ..items.registry import registry
        from ..run.decks import STARTING_DECKS

        deck = next((d for d in STARTING_DECKS if d.id == self.deck_id), None)
        if deck is not None:
            self.economy.money = deck.initial_money
            for joker_id in deck.initial_jokers:
                joker_cls = registry.get_joker(joker_id)
                if joker_cls:
                    self.jokers.append(joker_cls())
                    if self.profile:
                        self.profile.discover(joker_id)

            if deck.deck_modifications.get("free_planet"):
                import random

                planet_ids = list(registry.planets.keys())
                if planet_ids:
                    p_id = random.choice(planet_ids)
                    planet_cls = registry.get_planet(p_id)
                    if planet_cls:
                        # Applying planet effect immediately
                        if self.profile:
                            self.profile.discover(p_id)
                        pass  # Currently no contract tracking to apply to

    # ── Current blind target ───────────────────────────────
    @property
    def current_blind(self) -> Ante:
        from ..run.ante import ANTE_TABLE

        return ANTE_TABLE[self.ante_number - 1][self.blind_index]

    @property
    def target_score(self) -> int:
        return self.current_blind.target

    def advance_blind(self) -> None:
        if self.blind_index < 2:
            self.blind_index += 1
        elif self.ante_number < 8:
            self.ante_number += 1
            self.blind_index = 0
        else:
            self.run_won = True
