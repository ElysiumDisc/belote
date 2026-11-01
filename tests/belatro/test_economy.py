"""Economy: money, interest, round-end payout."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TestEconomy:
    def setup_method(self) -> None:
        from belote.belatro.core.economy import Economy

        self.eco = Economy()

    def test_default_money_is_zero(self) -> None:
        assert self.eco.money == 0

    def test_add_money_increases_money(self) -> None:
        self.eco.add_money(10)
        assert self.eco.money == 10

    def test_add_money_accumulates(self) -> None:
        self.eco.add_money(5)
        self.eco.add_money(3)
        assert self.eco.money == 8

    def test_add_money_rejects_negative(self) -> None:
        """4.6.4: symmetry with `spend_money`. A negative `amount` would
        silently drain the balance; spend operations must go through
        `spend_money` (balance-checked). Loud failure beats silent drain."""
        import pytest as _pt

        with _pt.raises(ValueError):
            self.eco.add_money(-5)
        assert self.eco.money == 0

    def test_spend_money_success_returns_true(self) -> None:
        self.eco.money = 20
        result = self.eco.spend_money(15)
        assert result is True
        assert self.eco.money == 5

    def test_spend_money_exact_amount_succeeds(self) -> None:
        self.eco.money = 10
        result = self.eco.spend_money(10)
        assert result is True
        assert self.eco.money == 0

    def test_spend_money_insufficient_returns_false(self) -> None:
        self.eco.money = 5
        result = self.eco.spend_money(10)
        assert result is False
        assert self.eco.money == 5  # unchanged

    def test_spend_money_zero_always_succeeds(self) -> None:
        result = self.eco.spend_money(0)
        assert result is True

    def test_calculate_interest_rate_zero_returns_zero(self) -> None:
        self.eco.money = 100
        self.eco.interest_rate = 0
        assert self.eco.calculate_interest() == 0

    def test_calculate_interest_rate_one_basic(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=15, interest_rate=1, max_interest=5)
        # 15 // 5 * 1 = 3
        assert eco.calculate_interest() == 3

    def test_calculate_interest_capped_at_max_interest(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=100, interest_rate=1, max_interest=5)
        # 100 // 5 * 1 = 20 → capped at 5
        assert eco.calculate_interest() == 5

    def test_calculate_interest_fractional_money_floors(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=14, interest_rate=1, max_interest=10)
        # 14 // 5 = 2 → interest = 2
        assert eco.calculate_interest() == 2

    def test_process_round_end_no_overflow_gives_base(self) -> None:
        # 50 pts over target → 50 // 10 = 5
        payout = self.eco.process_round_end(50)
        assert payout == 5
        assert self.eco.money == 5

    def test_process_round_end_adds_interest(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=10, interest_rate=1, max_interest=5)
        # 30 over → 3 base + 10//5 interest = 3 + 2 = 5
        payout = eco.process_round_end(30)
        assert payout == 5
        assert eco.money == 15

    def test_process_round_end_negative_pts_gives_zero(self) -> None:
        payout = self.eco.process_round_end(-100)
        assert payout == 0
        assert self.eco.money == 0

    def test_process_round_end_zero_pts_gives_zero_base(self) -> None:
        payout = self.eco.process_round_end(0)
        assert payout == 0
