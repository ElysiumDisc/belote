from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Economy:
    """Handles money tracking, interest, and round payouts."""

    money: int = 0
    interest_rate: int = 0  # default 0, becomes 1 with La Voute voucher
    max_interest: int = 0  # default 0, becomes 5 with La Voute voucher
    bonus_per_round: int = 0  # flat bonus paid each round end (La Télescope)

    def add_money(self, amount: int) -> None:
        # 4.6.4: reject negative amounts for symmetry with `spend_money`. A
        # caller passing a negative `amount` would otherwise silently drain
        # the player's balance via `money += -N`. Spend operations must go
        # through `spend_money` (which is balance-checked); a bug that
        # routes a "credit" through `add_money(-X)` is the wrong code path
        # and should fail loudly.
        if amount < 0:
            raise ValueError(
                f"Economy.add_money expects a non-negative amount; got {amount}. "
                "Use spend_money() for debits."
            )
        self.money += amount

    def spend_money(self, amount: int) -> bool:
        # Reject negative amounts: a negative `amount` would otherwise pass
        # `money >= amount` trivially and credit the player via the
        # `money -= amount` line. Zero is a benign no-op spend.
        if amount < 0:
            return False
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
        """Calculate payout: $1 per 10pts over target + interest + flat bonus."""
        base_payout = max(0, points_over_target // 10)
        interest = self.calculate_interest()
        total = base_payout + interest + self.bonus_per_round
        self.add_money(total)
        return total
