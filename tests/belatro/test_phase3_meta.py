"""Phase 3 tests: ante themes, endless mode, joker fusion."""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.items.base import (
    FusionError,
    Joker,
    JokerResult,
    Rarity,
    fuse_jokers,
)
from belote.belatro.run.ante import calculate_target, endless_ante
from belote.belatro.run.ante_themes import (
    ALL_ANTE_THEMES,
    THEME_BY_ID,
    CafeAnte,
    TournoiAnte,
    roll_theme,
)

# ── Ante themes ─────────────────────────────────────────────────────────────


def test_all_themes_registered_in_lookup() -> None:
    assert {t().id for t in ALL_ANTE_THEMES} == {"cafe", "tournoi"}
    assert THEME_BY_ID["cafe"] is CafeAnte
    assert THEME_BY_ID["tournoi"] is TournoiAnte


def test_roll_theme_pdf() -> None:
    # 0.0 → cafe, 0.20 → tournoi, 0.50 → None
    assert isinstance(roll_theme(0.0), CafeAnte)
    assert isinstance(roll_theme(0.20), TournoiAnte)
    assert roll_theme(0.50) is None


def test_cafe_ante_grants_starting_chips_and_softens_boss() -> None:
    run = BelAtroRun()
    base_chips = run.permanent_chips
    theme = CafeAnte()
    theme.on_ante_start(run)
    assert run.permanent_chips == base_chips + 25
    assert theme.target_multiplier(0) == 1.0
    assert theme.target_multiplier(2) == 0.95


def test_cafe_ante_blind_won_lifts_trust() -> None:
    run = BelAtroRun()
    starting_trust = run.partner.trust.value
    CafeAnte().on_blind_won(run, blind_index=1)
    assert run.partner.trust.value == starting_trust + 1


def test_tournoi_ante_sets_coinche_flag_and_pays_money() -> None:
    run = BelAtroRun()
    starting_money = run.economy.money
    theme = TournoiAnte()
    theme.on_ante_start(run)
    assert run.card_enhancements.get("always_offer_coinche") is True
    theme.on_blind_won(run, blind_index=0)
    assert run.economy.money > starting_money


# ── Endless mode ────────────────────────────────────────────────────────────


def test_advance_blind_at_ante_8_blind_2_sets_run_won_when_not_endless() -> None:
    run = BelAtroRun(ante_number=8, blind_index=2)
    run.advance_blind()
    assert run.run_won is True
    assert run.endless_ante_offset == 0


def test_advance_blind_at_ante_8_blind_2_loops_in_endless() -> None:
    run = BelAtroRun(ante_number=8, blind_index=2, endless=True)
    run.advance_blind()
    assert run.run_won is False
    assert run.ante_number == 8
    assert run.blind_index == 0
    assert run.endless_ante_offset == 1


def test_endless_target_scales_super_exponentially() -> None:
    # Each endless offset multiplies target by ×2.2 (modulo int truncation).
    base = calculate_target(8, 2, endless_offset=0)
    one_loop = calculate_target(8, 2, endless_offset=1)
    two_loops = calculate_target(8, 2, endless_offset=2)
    # Allow ±1 tolerance from float→int truncation.
    assert abs(one_loop - int(base * 2.2)) <= 1
    assert abs(two_loops - int(base * 2.2 * 2.2)) <= 1
    # And the curve is strictly increasing.
    assert base < one_loop < two_loops


def test_current_blind_uses_endless_targets_when_endless_active() -> None:
    run = BelAtroRun(ante_number=8, blind_index=0, endless=True, endless_ante_offset=2)
    blind = run.current_blind
    expected = endless_ante(8, 0, 2)
    assert blind.target == expected.target


def test_enter_endless_clears_run_won_and_flips_flag() -> None:
    run = BelAtroRun(run_won=True)
    run.enter_endless()
    assert run.endless is True
    assert run.run_won is False


# ── Joker fusion ────────────────────────────────────────────────────────────


class _StubJoker(Joker):
    id = "stub_a"
    name = "Stub A"
    description = ""

    def on_round_start(self, state: dict) -> JokerResult | None:
        return None


class _StubJokerB(Joker):
    id = "stub_b"
    name = "Stub B"
    description = ""

    def on_round_start(self, state: dict) -> JokerResult | None:
        return None


def test_fusion_bumps_rarity_one_tier() -> None:
    a = _StubJoker()
    b = _StubJokerB()
    fused = fuse_jokers(a, b)
    assert fused.rarity == Rarity.UNCOMMON  # COMMON + COMMON → UNCOMMON
    assert fused.fusable is False
    assert "Stub A" in fused.name and "Stub B" in fused.name


def test_fusion_clamps_at_rare() -> None:
    a = _StubJoker()
    a.rarity = Rarity.RARE
    b = _StubJokerB()
    b.rarity = Rarity.RARE
    fused = fuse_jokers(a, b)
    # RARE + RARE clamps at RARE — never auto-promotes to LEGENDARY.
    assert fused.rarity == Rarity.RARE


def test_fusion_rejects_legendary() -> None:
    a = _StubJoker()
    a.rarity = Rarity.LEGENDARY
    b = _StubJokerB()
    try:
        fuse_jokers(a, b)
    except FusionError:
        return
    raise AssertionError("Expected FusionError for legendary input")


def test_fusion_rejects_unfusable() -> None:
    a = _StubJoker()
    a.fusable = False
    b = _StubJokerB()
    try:
        fuse_jokers(a, b)
    except FusionError:
        return
    raise AssertionError("Expected FusionError for fusable=False input")


def test_fused_joker_cannot_be_refused() -> None:
    a = _StubJoker()
    b = _StubJokerB()
    once = fuse_jokers(a, b)
    twice_input = _StubJoker()
    try:
        fuse_jokers(once, twice_input)
    except FusionError:
        return
    raise AssertionError("Fused jokers should be flagged fusable=False")
