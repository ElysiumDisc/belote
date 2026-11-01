"""BelAtroRun state, ante table and seeded boss selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


class TestBelAtroRun:
    def setup_method(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun

        self.run = BelAtroRun()

    def test_default_ante_is_one(self) -> None:
        assert self.run.ante_number == 1

    def test_default_blind_index_is_zero(self) -> None:
        assert self.run.blind_index == 0

    def test_default_run_over_is_false(self) -> None:
        assert self.run.run_over is False

    def test_default_run_won_is_false(self) -> None:
        assert self.run.run_won is False

    def test_default_deck_id(self) -> None:
        assert self.run.deck_id == "classique"

    def test_target_score_ante1_blind0(self) -> None:
        assert self.run.target_score == 100

    def test_current_blind_is_small_blind(self) -> None:
        assert self.run.current_blind.name == "Small Blind"

    def test_advance_blind_zero_to_one(self) -> None:
        self.run.advance_blind()
        assert self.run.blind_index == 1

    def test_advance_blind_one_to_two(self) -> None:
        self.run.blind_index = 1
        self.run.advance_blind()
        assert self.run.blind_index == 2

    def test_advance_blind_two_goes_to_next_ante(self) -> None:
        self.run.blind_index = 2
        self.run.advance_blind()
        assert self.run.ante_number == 2
        assert self.run.blind_index == 0

    def test_advance_blind_wraps_correctly_across_antes(self) -> None:
        # Advance from 1-0 through to 2-1
        self.run.advance_blind()  # → 1-1
        self.run.advance_blind()  # → 1-2
        self.run.advance_blind()  # → 2-0
        assert self.run.ante_number == 2
        assert self.run.blind_index == 0

    def test_advance_blind_ante8_boss_sets_run_won(self) -> None:
        self.run.ante_number = 8
        self.run.blind_index = 2
        self.run.advance_blind()
        assert self.run.run_won is True

    def test_run_not_won_before_final_advance(self) -> None:
        self.run.ante_number = 8
        self.run.blind_index = 1
        self.run.advance_blind()
        assert self.run.run_won is False

    def test_target_score_changes_with_blind(self) -> None:
        self.run.advance_blind()  # → big blind
        assert self.run.target_score == 150

    def test_economy_defaults(self) -> None:
        assert self.run.economy.money == 4  # classique deck starts with 4

    def test_joker_slots_default(self) -> None:
        from belote.belatro.core.run_state import MAX_JOKER_SLOTS

        assert self.run.joker_slots == MAX_JOKER_SLOTS

    def test_show_north_hand_default_false(self) -> None:
        assert self.run.show_north_hand is False


class TestAnteTable:
    def setup_method(self) -> None:
        from belote.belatro.run.ante import ANTE_TABLE, calculate_target

        self.ANTE_TABLE = ANTE_TABLE
        self.calculate_target = calculate_target

    def test_table_has_eight_antes(self) -> None:
        assert len(self.ANTE_TABLE) == 8

    def test_each_ante_has_three_blinds(self) -> None:
        for row in self.ANTE_TABLE:
            assert len(row) == 3

    def test_first_blind_is_small(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[0].name == "Small Blind"

    def test_second_blind_is_big(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[1].name == "Big Blind"

    def test_third_blind_is_boss(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[2].name == "Boss Blind"

    def test_targets_increase_across_antes(self) -> None:
        for i in range(len(self.ANTE_TABLE) - 1):
            assert self.ANTE_TABLE[i][0].target < self.ANTE_TABLE[i + 1][0].target

    def test_within_ante_targets_increase_with_blind(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[0].target < row[1].target < row[2].target

    def test_ante1_small_target_is_100(self) -> None:
        assert self.ANTE_TABLE[0][0].target == 100

    def test_ante1_big_target_is_150(self) -> None:
        assert self.ANTE_TABLE[0][1].target == 150

    def test_ante1_boss_target_is_200(self) -> None:
        assert self.ANTE_TABLE[0][2].target == 200

    def test_calculate_target_ante1_small(self) -> None:
        assert self.calculate_target(1, 0) == 100

    def test_calculate_target_ante1_big(self) -> None:
        assert self.calculate_target(1, 1) == 150

    def test_calculate_target_ante1_boss(self) -> None:
        assert self.calculate_target(1, 2) == 200

    def test_calculate_target_scales_with_ante(self) -> None:
        target_a1 = self.calculate_target(1, 0)
        target_a2 = self.calculate_target(2, 0)
        # Ante 2 should be 1.5x ante 1
        assert target_a2 == pytest.approx(target_a1 * 1.5, abs=1)

    def test_ante_numbers_are_correct(self) -> None:
        for i, row in enumerate(self.ANTE_TABLE):
            for blind in row:
                assert blind.number == i + 1


class TestBossSelectionDeterminism:
    """F2: BelAtroGame._play_blind now picks the boss via run._get_rng()
    instead of the module-level random.choice. Same fix class as 3.2.0 for
    shop and tarots; boss was the last unseeded RNG site."""

    def test_seeded_runs_pick_same_boss_class(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun
        from belote.belatro.run.boss import ALL_BOSS_MODIFIERS

        run1 = BelAtroRun(seed=42)
        run2 = BelAtroRun(seed=42)
        # The exact call _play_blind now performs.
        b1 = run1._get_rng().choice(ALL_BOSS_MODIFIERS)
        b2 = run2._get_rng().choice(ALL_BOSS_MODIFIERS)
        assert b1 is b2

    def test_play_blind_does_not_use_module_random_for_boss(self) -> None:
        """Source-level guard: the pre-3.3.3 anti-pattern
        `random.choice(ALL_BOSS_MODIFIERS)` must not return. If someone
        reverts to module-level random, this fails before the determinism
        regression can ship.
        """
        import inspect

        from belote.belatro.main import BelAtroGame

        source = inspect.getsource(BelAtroGame)
        assert "random.choice(ALL_BOSS_MODIFIERS)" not in source, (
            "Boss selection must go through self.run._get_rng().choice() — see 3.3.3 F2."
        )
