from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Economy:
    """Handles money tracking, interest, and round payouts."""

    money: int = 0
    interest_rate: int = 0  # default 0, becomes 1 with La Voute voucher
    max_interest: int = 0  # default 0, becomes 5 with La Voute voucher

    def add_money(self, amount: int) -> None:
        self.money += amount

    def spend_money(self, amount: int) -> bool:
        if self.money >= amount:
            self.money -= amount
            return True
        return False

    def calculate_interest(self) -> int:
        if self.interest_rate == 0:
            return 0
        interest = (self.money // 5) * self.interest_rate
        return min(interest, self.max_interest)

    def process_round_end(self, points_over_target: int) -> int:
        """Calculate payout: $1 per 10pts over target + interest."""
        base_payout = max(0, points_over_target // 10)
        interest = self.calculate_interest()
        total = base_payout + interest
        self.add_money(total)
        return total
