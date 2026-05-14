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
        # Bumped on every register_* call; the get_available_* caches key on
        # this so a re-registration invalidates the cache automatically.
        self._gen: int = 0
        self._jokers_cache: dict[
            tuple[int, frozenset[str] | None], dict[str, type[Joker]]
        ] = {}
        self._vouchers_cache: dict[
            tuple[int, frozenset[str] | None], dict[str, type[Voucher]]
        ] = {}

    def _bump(self) -> None:
        self._gen += 1
        self._jokers_cache.clear()
        self._vouchers_cache.clear()

    def register_joker(self, joker_cls: type[Joker]) -> None:
        existing = self.jokers.get(joker_cls.id)
        assert existing is None or existing is joker_cls, (
            f"duplicate joker id {joker_cls.id!r}: "
            f"{existing.__name__} vs {joker_cls.__name__}"
        )
        self.jokers[joker_cls.id] = joker_cls
        self._bump()

    def register_planet(self, planet_cls: type[Planet]) -> None:
        existing = self.planets.get(planet_cls.id)
        assert existing is None or existing is planet_cls, (
            f"duplicate planet id {planet_cls.id!r}: "
            f"{existing.__name__} vs {planet_cls.__name__}"
        )
        self.planets[planet_cls.id] = planet_cls
        self._bump()

    def register_tarot(self, tarot_cls: type[Tarot]) -> None:
        existing = self.tarots.get(tarot_cls.id)
        assert existing is None or existing is tarot_cls, (
            f"duplicate tarot id {tarot_cls.id!r}: "
            f"{existing.__name__} vs {tarot_cls.__name__}"
        )
        self.tarots[tarot_cls.id] = tarot_cls
        self._bump()

    def register_voucher(self, voucher_cls: type[Voucher]) -> None:
        existing = self.vouchers.get(voucher_cls.id)
        assert existing is None or existing is voucher_cls, (
            f"duplicate voucher id {voucher_cls.id!r}: "
            f"{existing.__name__} vs {voucher_cls.__name__}"
        )
        self.vouchers[voucher_cls.id] = voucher_cls
        self._bump()

    def get_joker(self, item_id: str) -> type[Joker] | None:
        return self.jokers.get(item_id)

    def get_planet(self, item_id: str) -> type[Planet] | None:
        return self.planets.get(item_id)

    def get_tarot(self, item_id: str) -> type[Tarot] | None:
        return self.tarots.get(item_id)

    def get_voucher(self, item_id: str) -> type[Voucher] | None:
        return self.vouchers.get(item_id)

    @staticmethod
    def _profile_key(profile: Profile | None) -> frozenset[str] | None:
        # Cache key includes the unlock set so different profiles get
        # independent cached views without leaking across runs.
        return frozenset(profile.unlocked_ids) if profile is not None else None

    def get_available_jokers(self, profile: Profile | None) -> dict[str, type[Joker]]:
        key = (self._gen, self._profile_key(profile))
        cached = self._jokers_cache.get(key)
        if cached is not None:
            return cached
        result = {
            k: v
            for k, v in self.jokers.items()
            if not getattr(v, "is_unlockable", False)
            or (profile is not None and profile.is_unlocked(k))
        }
        self._jokers_cache[key] = result
        return result

    def get_available_vouchers(self, profile: Profile | None) -> dict[str, type[Voucher]]:
        key = (self._gen, self._profile_key(profile))
        cached = self._vouchers_cache.get(key)
        if cached is not None:
            return cached
        result = {
            k: v
            for k, v in self.vouchers.items()
            if not getattr(v, "is_unlockable", False)
            or (profile is not None and profile.is_unlocked(k))
        }
        self._vouchers_cache[key] = result
        return result


# Global registry instance
registry = ItemRegistry()

# Module-level guard against repeated full re-walks. Tests that build many
# BelAtroRun instances (each calls register_all_items lazily) used to redo the
# 4× dir(mod) walk + class registration on every run; the cache bump in
# ItemRegistry meant downstream `get_available_*` cached views were also
# invalidated. The first call wins; subsequent calls are no-ops.
_registered: bool = False


def register_all_items() -> None:
    global _registered
    # Guard against repeated full re-walks. The second clause re-runs when a
    # caller has swapped in a fresh empty ItemRegistry (the test-suite pattern
    # at tests/belatro/test_belatro.py::TestItemRegistry.setup_method) — those
    # callers expect a populated registry on return.
    if _registered and registry.jokers:
        return
    from . import planets, tarots, vouchers
    from .jokers import (
        annonces,
        coinche,
        contract,
        corrupted,
        economy,
        hand_comp,
        trick_timing,
    )
    from .partner_jokers import passive, risky, shaper

    # Jokers
    for mod in [
        trick_timing,
        hand_comp,
        contract,
        economy,
        corrupted,
        passive,
        shaper,
        risky,
        coinche,
        annonces,
    ]:
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

    # 3.6.0: enforce that the HUD synergy registry references only real joker
    # IDs. Catches typos at module-init time rather than letting the badge
    # silently never fire. Use an explicit raise (not `assert`) so the check
    # survives `python -O` / `PYTHONOPTIMIZE=1` in packaged installs. Imported
    # lazily to avoid a circular import at module load.
    from ..ui.hud import validate_synergy_ids

    missing = validate_synergy_ids()
    if missing:
        raise RuntimeError(
            f"belatro/ui/hud.py::_SYNERGY_PAIRS references unregistered joker IDs: "
            f"{missing}. Either register the joker or remove the pair."
        )

    _registered = True
