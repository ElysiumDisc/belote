"""4.6.2 audit matrix — per-boss contract pins.

Each test verifies a boss's `apply()` produces the correct `BossModifiers`
flag, and (where the flag is non-trivial) at least one downstream read site
honours it. The declarations_zero × BelAtro accumulator fix from the
4.6.2 audit is pinned in its own focused test below.
"""

from __future__ import annotations

import pytest

from belote.belatro.engine.event_bus import DeclarationScoredEvent
from belote.belatro.engine.modifier_patch import PatchedGameState
from belote.belatro.run.boss import (
    ALL_BOSS_MODIFIERS,
    BetrayalArc,
    BossModifier,
    LaCompetition,
    LAgentDoubleBoss,
    LaGrandeMuette,
    LaMalediction,
    LAnarchie,
    LaReineNoire,
    LaRupture,
    LaSolitude,
    LAvocat,
    LeBrouillard,
    LeDeluge,
    LeDivorce,
    LeFantomePartenaire,
    LeMime,
    LeRoiMort,
    LeSauvage,
    LesClubsBannis,
    LesDixMaudits,
    LeZeroFinal,
    LIconoclaste,
)
from belote.game import BossModifiers, Seat, new_game

# ── Registry invariant ────────────────────────────────────────────────────


def test_all_21_bosses_registered() -> None:
    """Audit invariant: ALL_BOSS_MODIFIERS must contain every concrete boss.
    Pinning the count surfaces accidental omissions when adding a new boss."""
    assert len(ALL_BOSS_MODIFIERS) == 21


@pytest.mark.parametrize("boss_cls", ALL_BOSS_MODIFIERS)
def test_every_boss_has_id_name_description(boss_cls: type[BossModifier]) -> None:
    inst = boss_cls()
    assert isinstance(inst.id, str) and inst.id
    assert isinstance(inst.name, str) and inst.name
    assert isinstance(inst.description, str) and inst.description


# ── Per-boss flag mapping ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("boss_cls", "expected_flag"),
    [
        (LaGrandeMuette, "no_belote"),
        (LAnarchie, "dynamic_trump"),
        (LeRoiMort, "kings_zero"),
        (LaMalediction, "invert_scoring"),
        (LAvocat, "auto_coinche"),
        (LeDeluge, "seven_eight_trump"),
        (LaReineNoire, "queen_spades_penalty"),
        (LeBrouillard, "hide_hud"),
        (LesClubsBannis, "ban_clubs"),
        (LeZeroFinal, "no_dix_de_der"),
        (LesDixMaudits, "tens_zero"),
        (LaRupture, "no_consecutive_team_wins"),
        (LeFantomePartenaire, "hide_partner_hand"),
        (LAgentDoubleBoss, "agent_double_active"),
        (LaSolitude, "partner_forced_pass"),
        (LeDivorce, "lock_trust_zero"),
        (LaCompetition, "separate_scoring"),
        (LeSauvage, "aces_zero"),
        (LIconoclaste, "jacks_zero"),
        (LeMime, "declarations_zero"),
    ],
)
def test_boss_sets_expected_flag(boss_cls: type[BossModifier], expected_flag: str) -> None:
    """flags() returns BossModifiers; the corresponding field must be True
    while no unrelated field is accidentally flipped."""
    flags = boss_cls().flags()
    assert isinstance(flags, BossModifiers)
    assert getattr(flags, expected_flag) is True, (
        f"{boss_cls.__name__} did not set {expected_flag}"
    )


def test_betrayal_arc_sets_three_flags() -> None:
    """BetrayalArc is the only multi-flag boss: lock_trust_zero +
    agent_double_active + agent_double_late_only."""
    flags = BetrayalArc().flags()
    assert flags.lock_trust_zero is True
    assert flags.agent_double_active is True
    assert flags.agent_double_late_only is True


# ── Foot-gun: no boss reads a flag via the `_X` anti-pattern ──────────────


def test_no_underscore_boss_read_pattern_in_src() -> None:
    """Locks against `getattr(state, '_X', False)` foot-gun across the BelAtro
    tree. Boss flags MUST be read as `state.boss_modifiers.X`."""
    import re
    from pathlib import Path

    src_root = Path(__file__).parent.parent.parent / "src" / "belote"
    boss_field_names = [f.name for f in BossModifiers.__dataclass_fields__.values()]
    pattern = re.compile(
        r'getattr\(\s*state\s*,\s*["\'](_(' + "|".join(boss_field_names) + r'))["\']'
    )
    offenders: list[tuple[Path, int, str]] = []
    for path in src_root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append((path, lineno, line.strip()))
    assert not offenders, f"Underscore-boss-read foot-gun detected: {offenders}"


# ── 4.6.2 fix: declarations_zero must propagate to BelAtro accumulator ────


def test_le_mime_zeros_event_points_in_belatro_path() -> None:
    """4.6.2 audit fix: pre-fix, the BelAtro accumulator's DeclarationScoredEvent
    branch added raw `event.points` to chips and fired on_declaration jokers
    (LeMathematicien, QuinteRoyale) on raw points — bypassing LeMime's
    'declarations score 0' promise. Round_driver now zeros pts when
    `declarations_zero` is set.

    Direct grep on the source: round_driver.py emits points=0 under the flag.
    """
    from pathlib import Path

    rd = (
        Path(__file__).parent.parent.parent
        / "src" / "belote" / "belatro" / "engine" / "round_driver.py"
    )
    text = rd.read_text()
    assert "declarations_zero" in text, (
        "round_driver must read state.boss_modifiers.declarations_zero "
        "to zero declaration points before emit"
    )
    # Round-trip through the LeMathematicien gate: with points=0 (as
    # round_driver now emits under LeMime) the joker stays silent.
    from belote.belatro.items.jokers.annonces import LeMathematicien

    ev_zero = DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=0)
    assert LeMathematicien().on_declaration(ev_zero, {}) is None


def test_le_mime_and_quinte_royale_do_not_double_credit() -> None:
    """Composition pin: under LeMime, QuinteRoyale must not arm — events
    fire with points=0 by the new round_driver gate."""
    from belote.belatro.items.jokers.annonces import QuinteRoyale

    j = QuinteRoyale()
    state: dict[str, object] = {}
    ev = DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=0)
    j.on_declaration(ev, state)
    assert f"{j.id}_armed" not in state


# ── Combo: high-risk pair fuzz tests ──────────────────────────────────────


def test_rupture_anarchie_combo_flags_set() -> None:
    """LaRupture + LAnarchie active simultaneously — both flags must hold
    on the same BossModifiers instance after sequential apply()."""
    state = PatchedGameState(new_game())
    LaRupture().apply(state)
    LAnarchie().apply(state)
    bm = state.boss_modifiers
    assert bm.no_consecutive_team_wins is True
    assert bm.dynamic_trump is True


def test_competition_malediction_combo_flags_set() -> None:
    state = PatchedGameState(new_game())
    LaCompetition().apply(state)
    LaMalediction().apply(state)
    bm = state.boss_modifiers
    assert bm.separate_scoring is True
    assert bm.invert_scoring is True


def test_three_zero_rank_bosses_combo() -> None:
    """LeRoiMort + LeSauvage + LIconoclaste = honors-suit becomes 7/8/9/10-only
    in trick value terms. Boss flags must all hold simultaneously."""
    state = PatchedGameState(new_game())
    LeRoiMort().apply(state)
    LeSauvage().apply(state)
    LIconoclaste().apply(state)
    bm = state.boss_modifiers
    assert bm.kings_zero is True
    assert bm.aces_zero is True
    assert bm.jacks_zero is True


def test_betrayal_arc_with_solitude_compounds_isolation() -> None:
    """BetrayalArc + LaSolitude = partner is forced to pass AND will sabotage
    from trick 4. Both regimes coexist on the same boss_modifiers."""
    state = PatchedGameState(new_game())
    BetrayalArc().apply(state)
    LaSolitude().apply(state)
    bm = state.boss_modifiers
    assert bm.partner_forced_pass is True
    assert bm.agent_double_active is True
    assert bm.agent_double_late_only is True
    assert bm.lock_trust_zero is True


# ── Boss id strings: not allowed in scoring / joker / round_driver ────────


def test_no_boss_id_string_branching_in_runtime() -> None:
    """Locks against `boss.id == 'la_grande_muette'`-style string branching in
    runtime code. All branching MUST go through `state.boss_modifiers.X`.
    `belatro/main.py` is permitted to reference ids for the ante UI label only."""
    import re
    from pathlib import Path

    src_root = Path(__file__).parent.parent.parent / "src" / "belote"
    boss_ids = [boss_cls().id for boss_cls in ALL_BOSS_MODIFIERS]
    pattern = re.compile(r'boss\.id\s*==')

    runtime_files = [
        src_root / "belatro" / "engine" / "round_driver.py",
        src_root / "belatro" / "core" / "scoring.py",
        src_root / "scoring.py",
        src_root / "game.py",
        src_root / "ai.py",
    ]
    offenders: list[tuple[Path, int, str]] = []
    for path in runtime_files:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                # Reject if the comparison RHS literally matches a known boss id.
                for bid in boss_ids:
                    if f'"{bid}"' in line or f"'{bid}'" in line:
                        offenders.append((path, lineno, line.strip()))
                        break
    assert not offenders, (
        f"Boss.id string branching detected in runtime code; use "
        f"state.boss_modifiers.X instead: {offenders}"
    )
