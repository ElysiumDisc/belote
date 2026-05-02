from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Joker, Planet, Tarot, Voucher

if TYPE_CHECKING:
    from ..progression.save import Profile


class ItemRegistry:
    """Dynamic lookup for all collectible items."""

    def __init__(self) -> None:
        self.jokers: dict[str, type[Joker]] = {}
        self.planets: dict[str, type[Planet]] = {}
        self.tarots: dict[str, type[Tarot]] = {}
        self.vouchers: dict[str, type[Voucher]] = {}

    def register_joker(self, joker_cls: type[Joker]) -> None:
        self.jokers[joker_cls.id] = joker_cls

    def register_planet(self, planet_cls: type[Planet]) -> None:
        self.planets[planet_cls.id] = planet_cls

    def register_tarot(self, tarot_cls: type[Tarot]) -> None:
        self.tarots[tarot_cls.id] = tarot_cls

    def register_voucher(self, voucher_cls: type[Voucher]) -> None:
        self.vouchers[voucher_cls.id] = voucher_cls

    def get_joker(self, item_id: str) -> type[Joker] | None:
        return self.jokers.get(item_id)

    def get_planet(self, item_id: str) -> type[Planet] | None:
        return self.planets.get(item_id)

    def get_tarot(self, item_id: str) -> type[Tarot] | None:
        return self.tarots.get(item_id)

    def get_voucher(self, item_id: str) -> type[Voucher] | None:
        return self.vouchers.get(item_id)

    def get_available_jokers(self, profile: Profile) -> dict[str, type[Joker]]:
        return {
            k: v
            for k, v in self.jokers.items()
            if profile.is_unlocked(k) or not getattr(v, "is_unlockable", False)
        }

    def get_available_vouchers(self, profile: Profile) -> dict[str, type[Voucher]]:
        return {
            k: v
            for k, v in self.vouchers.items()
            if profile.is_unlocked(k) or not getattr(v, "is_unlockable", False)
        }


# Global registry instance
registry = ItemRegistry()


def register_all_items() -> None:
    from . import planets, tarots, vouchers
    from .jokers import contract, corrupted, economy, hand_comp, trick_timing
    from .partner_jokers import passive, risky, shaper

    # Jokers
    for mod in [trick_timing, hand_comp, contract, economy, corrupted, passive, shaper, risky]:
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if isinstance(attr, type) and issubclass(attr, Joker) and attr is not Joker:
                registry.register_joker(attr)

    # Planets
    for attr_name in dir(planets):
        attr = getattr(planets, attr_name)
        if isinstance(attr, type) and issubclass(attr, Planet) and attr is not Planet:
            registry.register_planet(attr)

    # Tarots
    for attr_name in dir(tarots):
        attr = getattr(tarots, attr_name)
        if isinstance(attr, type) and issubclass(attr, Tarot) and attr is not Tarot:
            registry.register_tarot(attr)

    # Vouchers
    for attr_name in dir(vouchers):
        attr = getattr(vouchers, attr_name)
        if isinstance(attr, type) and issubclass(attr, Voucher) and attr is not Voucher:
            registry.register_voucher(attr)
