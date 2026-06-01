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

import pytest

from belote.belatro.items.registry import register_all_items, registry

# Audited census (4.9.6). Bump deliberately when items are intentionally added.
_EXPECTED_COUNTS = {
    "jokers": 42,
    "planets": 8,
    "tarots": 12,
    "vouchers": 12,
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
