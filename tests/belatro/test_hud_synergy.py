"""3.0.1 HUD synergy registry tests.

Goals:
- Every ID in `_SYNERGY_PAIRS` resolves to a real joker (no typos).
- `detect_synergies` reports the right pair for a known combo.
- `detect_synergies` falls back to a generic "stack" badge for 3+ unrelated
  jokers.
"""

from __future__ import annotations

from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.ui.hud import _SYNERGY_PAIRS, detect_synergies, validate_synergy_ids


def setup_module(module: object) -> None:
    register_all_items()


def test_every_synergy_id_resolves_to_a_real_joker() -> None:
    """If the synergy registry drifts, this fails loud rather than silently
    producing a no-op badge."""
    missing = validate_synergy_ids()
    assert missing == [], (
        f"_SYNERGY_PAIRS references jokers that don't exist: {missing}"
    )


def test_detect_synergies_finds_known_coinche_streak_pair() -> None:
    coinche_cls = registry.jokers["coinche_stack"]
    streak_cls = registry.jokers["tout_streak"]
    out = detect_synergies([coinche_cls(), streak_cls()])
    assert ("coinche_stack", "tout_streak") in out


def test_detect_synergies_finds_sentinelle_fanatique_pair() -> None:
    sent_cls = registry.jokers["la_sentinelle"]
    fan_cls = registry.jokers["le_fanatique"]
    out = detect_synergies([sent_cls(), fan_cls()])
    assert ("la_sentinelle", "le_fanatique") in out


def test_detect_synergies_generic_stack_badge_for_three_unrelated() -> None:
    """Three jokers with no known pair still raise a generic 'stack' tag."""
    # Pick three IDs that aren't part of any pair. Each pair entry is
    # (id_a, id_b, description) since 3.4.0 — pull the first two.
    pair_ids = {x for pair in _SYNERGY_PAIRS for x in pair[:2]}
    unrelated = [j for j_id, j in registry.jokers.items() if j_id not in pair_ids][:3]
    if len(unrelated) < 3:
        return  # not enough non-paired jokers — registry too small
    out = detect_synergies([cls() for cls in unrelated])
    assert any(label == "stack" for label, _ in out)


def test_detect_synergies_empty_for_unrelated_pair() -> None:
    """One unpaired + one unpaired = no badge, not even a generic one."""
    pair_ids = {x for pair in _SYNERGY_PAIRS for x in pair[:2]}
    unrelated = [j for j_id, j in registry.jokers.items() if j_id not in pair_ids][:2]
    if len(unrelated) < 2:
        return
    out = detect_synergies([cls() for cls in unrelated])
    assert out == []


def test_detect_synergies_does_not_fire_for_solo_half() -> None:
    """3.3.3 T3: a pair badge must NOT fire when only one half of the pair
    is owned. Trip-wire for any future change to detect_synergies that
    accidentally matches single jokers against pair entries.
    """
    for entry in _SYNERGY_PAIRS:
        left_id, right_id = entry[0], entry[1]
        # Confirm the right half is registered (the validate test above
        # already pins this, but be defensive).
        if right_id not in registry.jokers or left_id not in registry.jokers:
            continue
        left_cls = registry.jokers[left_id]
        out = detect_synergies([left_cls()])
        assert (left_id, right_id) not in out, (
            f"Pair ({left_id}, {right_id}) fired for solo {left_id}"
        )
        assert (right_id, left_id) not in out, (
            f"Pair ({right_id}, {left_id}) fired for solo {left_id}"
        )
