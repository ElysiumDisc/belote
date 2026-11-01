"""Registry-integrity pins (4.9.6).

`registry.{jokers,planets,tarots,vouchers}` are keyed by id, so a duplicate-id
registration silently *overwrites* the earlier item rather than erroring — the
dict just ends up one shorter. Pinning the category counts turns any such
accidental collision (or a dropped registration) into a test failure. Display
names are NOT dict keys, so name collisions are real and detectable; pin their
uniqueness too, since the shop/collection UIs identify items to the player by
name.

Counts pinned from the audit census run during the 4.9.6 review.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from belote.belatro.items.registry import register_all_items, registry

if TYPE_CHECKING:
    pass

# Audited census (4.9.6; 4.11.0: +12 jokers, +1 planet, +2 tarots, +1 voucher).
# Bump deliberately when items are intentionally added.
_EXPECTED_COUNTS = {
    "jokers": 54,
    "planets": 9,
    "tarots": 14,
    "vouchers": 13,
}


@pytest.fixture(autouse=True)
def _registered() -> None:
    register_all_items()


@pytest.mark.parametrize("category,expected", _EXPECTED_COUNTS.items())
def test_category_counts(category: str, expected: int) -> None:
    items = getattr(registry, category)
    assert len(items) == expected, (
        f"{category}: expected {expected}, got {len(items)} — a duplicate id may "
        "have overwritten an item, or a registration was dropped."
    )


@pytest.mark.parametrize("category", list(_EXPECTED_COUNTS))
def test_ids_match_keys(category: str) -> None:
    # Every item's own `.id` must equal the key it is registered under, else a
    # lookup by id would miss it.
    for key, item_cls in getattr(registry, category).items():
        assert item_cls().id == key, f"{category}: {item_cls.__name__}.id != key {key!r}"


def test_no_duplicate_display_names_across_all_items() -> None:
    names: dict[str, str] = {}
    collisions: list[str] = []
    for category in _EXPECTED_COUNTS:
        for item_cls in getattr(registry, category).values():
            name = item_cls().name
            if name in names:
                collisions.append(f"{name!r} in {category} collides with {names[name]}")
            else:
                names[name] = category
    assert not collisions, "duplicate display names: " + "; ".join(collisions)


class TestItemRegistry:
    def setup_method(self) -> None:
        from belote.belatro.items.registry import ItemRegistry, register_all_items

        # Use a fresh registry to avoid state leakage
        self.registry = ItemRegistry()
        # Monkey-patch the global for register_all_items
        import belote.belatro.items.registry as reg_mod

        self._orig_registry = reg_mod.registry
        reg_mod.registry = self.registry
        register_all_items()
        reg_mod.registry = self._orig_registry

    def test_jokers_nonempty_after_registration(self) -> None:
        assert len(self.registry.jokers) > 0

    def test_planets_nonempty_after_registration(self) -> None:
        assert len(self.registry.planets) > 0

    def test_tarots_nonempty_after_registration(self) -> None:
        assert len(self.registry.tarots) > 0

    def test_vouchers_nonempty_after_registration(self) -> None:
        assert len(self.registry.vouchers) > 0

    def test_get_joker_returns_class(self) -> None:
        first_id = next(iter(self.registry.jokers))
        cls = self.registry.get_joker(first_id)
        assert cls is not None

    def test_get_joker_unknown_returns_none(self) -> None:
        assert self.registry.get_joker("not_a_real_joker_id") is None

    def test_get_planet_returns_class(self) -> None:
        first_id = next(iter(self.registry.planets))
        cls = self.registry.get_planet(first_id)
        assert cls is not None

    def test_get_tarot_returns_class(self) -> None:
        first_id = next(iter(self.registry.tarots))
        cls = self.registry.get_tarot(first_id)
        assert cls is not None

    def test_get_voucher_returns_class(self) -> None:
        first_id = next(iter(self.registry.vouchers))
        cls = self.registry.get_voucher(first_id)
        assert cls is not None

    def test_le_premier_sang_registered(self) -> None:
        assert "le_premier_sang" in self.registry.jokers

    def test_le_miroir_registered(self) -> None:
        assert "le_miroir" in self.registry.jokers

    def test_get_available_jokers_excludes_locked(self) -> None:
        from belote.belatro.progression.save import Profile

        profile = Profile()
        available = self.registry.get_available_jokers(profile)
        # All non-unlockable jokers should be available
        for jid, jcls in available.items():
            assert not getattr(jcls, "is_unlockable", False) or profile.is_unlocked(jid)
