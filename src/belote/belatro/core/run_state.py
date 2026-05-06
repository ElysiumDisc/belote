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
DEFAULT_CONSUMABLE_SLOTS = 2


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
    consumables: list[Any] = field(default_factory=list)  # Tarot/Planet instances
    joker_slots: int = MAX_JOKER_SLOTS
    consumable_slots: int = DEFAULT_CONSUMABLE_SLOTS

    # ── Permanent run bonuses (from Tarot cards) ───────────
    permanent_chips: int = 0
    permanent_mult: float = 1.0

    # ── Voucher flags ───────────────────────────────────────
    guarantee_tarot_in_shop: bool = False
    show_partner_bid_tendency: bool = False
    tie_breaks_for_taker: bool = False
    partner_throws_trick: bool = False
    capot_insurance: bool = False  # one-shot: halve a chute loss

    # ── Phase 1+ feature flags ──────────────────────────────
    tierce_charges: int = 0
    legendary_unlocked: set[str] = field(default_factory=set)
    endless: bool = False
    endless_ante_offset: int = 0
    ante_theme: str | None = None
    partner_mood: str = "neutral"

    # ── Economy ────────────────────────────────────────────
    economy: Economy = field(default_factory=Economy)

    # ── Partner ────────────────────────────────────────────
    partner: PartnerState = field(default_factory=PartnerState)

    # ── Deck ───────────────────────────────────────────────
    deck_id: str = "classique"
    card_enhancements: dict[str, Any] = field(default_factory=dict)  # card_id → Enhancement
    show_north_hand: bool = False  # set True by LeCarnet voucher
    contract_levels: dict[str, Any] = field(default_factory=dict)  # contract_id → planet reward dict
    gold_seal_aces: bool = False  # L'Aristocrate: Aces won → +$1 each
    corrupted_pool_visible: bool = False  # L'Anarchiste: corrupted shop pool revealed
    surcoinche_unlocked: bool = False  # La Surcoinche voucher: enables AI surcoinche

    # ── Last consumable used (read by LeFou tarot) ─────────
    last_consumable_id: str | None = None

    # ── Determinism ────────────────────────────────────────
    seed: int | None = None
    _rng: Any = None

    def consume(self, item: Any, context: object = None) -> None:
        """Centralised consumable activation.

        Records the item id as the most recent consumable (so LeFou can copy
        it) and removes it from `consumables` if present, then dispatches to
        the right hook based on item type (Tarot vs Planet).
        """
        import contextlib

        from ..items.base import Planet, Tarot

        with contextlib.suppress(ValueError):
            self.consumables.remove(item)
        self.last_consumable_id = getattr(item, "id", None)
        if isinstance(item, Tarot):
            item.use(self, context)
        elif isinstance(item, Planet):
            item.use(self)

    def _get_rng(self) -> Any:
        """Per-run random.Random instance, seeded from `seed` when given."""
        if self._rng is None:
            import random as _random

            self._rng = _random.Random(self.seed) if self.seed is not None else _random.Random()
        return self._rng

    def __post_init__(self) -> None:
        from ..items.registry import register_all_items, registry
        from ..run.decks import STARTING_DECKS

        if not registry.planets:
            register_all_items()

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
                planet_ids = list(registry.planets.keys())
                if planet_ids:
                    p_id = self._get_rng().choice(planet_ids)
                    planet_cls = registry.get_planet(p_id)
                    if planet_cls:
                        if self.profile:
                            self.profile.discover(p_id)
                        planet_instance = planet_cls()
                        self.contract_levels[planet_instance.contract_id] = planet_instance.level_up_reward()

            # Phase 2.4 deck mods
            if deck.deck_modifications.get("start_chips_bonus"):
                self.permanent_chips += int(deck.deck_modifications["start_chips_bonus"])
            if deck.deck_modifications.get("start_coinched"):
                self.card_enhancements["start_coinched"] = True
            if deck.deck_modifications.get("announce_x2"):
                self.card_enhancements["announce_x2"] = True
            if deck.deck_modifications.get("no_belote_rebelote"):
                self.card_enhancements["no_belote_rebelote"] = True
            if deck.deck_modifications.get("gold_seal_aces"):
                self.gold_seal_aces = True
            if deck.deck_modifications.get("corrupted_pool_visible"):
                self.corrupted_pool_visible = True
            if self.deck_id == "republicain":
                # 7s/8s are wild; legal_cards reads this flag from _joker_state.
                self.card_enhancements["republicain_wild"] = True

    # ── Current blind target ───────────────────────────────
    @property
    def current_blind(self) -> Ante:
        from ..run.ante import ANTE_TABLE, endless_ante

        if self.endless and self.endless_ante_offset > 0:
            return endless_ante(self.ante_number, self.blind_index, self.endless_ante_offset)
        return ANTE_TABLE[self.ante_number - 1][self.blind_index]

    @property
    def target_score(self) -> int:
        return self.current_blind.target

    def advance_blind(self) -> None:
        if self.blind_index < 2:
            self.blind_index += 1
            return
        # End of an ante.
        if self.ante_number < 8:
            self.ante_number += 1
            self.blind_index = 0
            return
        # End of ante 8.
        if self.endless:
            # Stay at ante 8, increment endless offset, restart blind cycle.
            self.endless_ante_offset += 1
            self.blind_index = 0
            return
        # Standard run completion.
        self.run_won = True

    def enter_endless(self) -> None:
        """Toggle endless mode after beating ante 8."""
        self.endless = True
        self.run_won = False  # endless overrides run-won state
