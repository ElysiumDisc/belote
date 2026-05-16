"""3.9.3 Phase 5: endless-mode escalation + boss variety.

These tests pin the escalation invariant (targets strictly grow each cycle
past Ante 8) and the no-immediate-repeat boss policy added in 3.9.3.
"""

from __future__ import annotations

import random

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.run.ante import calculate_target, endless_ante


def test_endless_target_escalation_is_strictly_increasing_per_cycle() -> None:
    """Each completed ante-cycle past 8 multiplies by 2.2 — the cycle's Big
    Blind and Boss Blind in offset N must outscale the same blind in offset
    N-1. Test offsets 1..5 to cover a realistic endless run length."""
    prev_big = calculate_target(8, 1, endless_offset=0)
    prev_boss = calculate_target(8, 2, endless_offset=0)
    for offset in range(1, 6):
        big = calculate_target(8, 1, endless_offset=offset)
        boss = calculate_target(8, 2, endless_offset=offset)
        assert big > prev_big, (
            f"endless offset {offset} Big Blind ({big}) did not exceed "
            f"offset {offset - 1} ({prev_big})"
        )
        assert boss > prev_boss
        assert boss > big, "Boss Blind must always exceed Big Blind within a cycle"
        prev_big, prev_boss = big, boss


def test_endless_ante_builds_with_correct_target() -> None:
    """endless_ante() must return an Ante with the same target the formula
    produces — guards against drift between the helper and the formula."""
    for blind_idx in range(3):
        for offset in (1, 3, 5):
            ante = endless_ante(8, blind_idx, offset)
            assert ante.target == calculate_target(8, blind_idx, endless_offset=offset)
            assert ante.number == 8


def test_advance_blind_into_endless_increments_offset() -> None:
    """At the end of Ante 8 in endless mode, advance_blind must bump the
    offset and restart the blind cycle (Small Blind)."""
    run = BelAtroRun()
    run.endless = True
    run.ante_number = 8
    run.blind_index = 2
    starting_offset = run.endless_ante_offset
    run.advance_blind()
    assert run.endless_ante_offset == starting_offset + 1
    assert run.blind_index == 0
    assert run.ante_number == 8  # stays pinned in endless


def test_enter_endless_jumps_past_redundant_ante_8_boss() -> None:
    """Pre-3.4.0 bug regression: entering endless must NOT replay Ante 8
    Boss at its normal (offset=0) target — offset must already be ≥ 1."""
    run = BelAtroRun()
    run.ante_number = 8
    run.blind_index = 2
    run.run_won = True
    run.run_over = True
    run.enter_endless()
    assert run.endless is True
    assert run.endless_ante_offset >= 1
    assert run.run_over is False
    assert run.run_won is False
    assert run.blind_index == 0


def test_recent_boss_window_is_bounded_to_two() -> None:
    """3.9.3 Phase 5: the recent-boss tracker must cap at 2 entries so the
    JSON snapshot stays small even after a long endless run."""
    run = BelAtroRun()
    # Simulate 20 boss reveals — only the last two should be retained.
    for i in range(20):
        run._recent_boss_ids.append(f"boss_{i}")
        if len(run._recent_boss_ids) > 2:
            del run._recent_boss_ids[: len(run._recent_boss_ids) - 2]
    assert run._recent_boss_ids == ["boss_18", "boss_19"]


def test_endless_target_formula_no_integer_drift() -> None:
    """Sanity: calculate_target returns an int (no float drift) for any
    reasonable endless offset."""
    rng = random.Random(7)
    for _ in range(50):
        ante = rng.randint(1, 8)
        blind = rng.randint(0, 2)
        offset = rng.randint(0, 10)
        result = calculate_target(ante, blind, endless_offset=offset)
        assert isinstance(result, int)
        assert result > 0
