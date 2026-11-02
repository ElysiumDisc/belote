"""5.0.0 — L'Usurier: a loan event in the shop.

From Ante 2 the moneylender visits some shops (seeded per blind, so a run
always meets him at the same ones) and offers **$30** — one loan at a time.
The debt compounds **20% at the start of every ante** (rounded up) and can be
repaid, in part or in full, in any shop: the Repay button stays while you
owe him.

The tension: borrowed cash counts toward La Voûte's interest (capped at $5
a round) and the Dix de Der Heist needs a fat wallet, but the debt grows
faster than the cap can follow. Let it reach **$90** and L'Usurier seizes
what you have — your money first, then your jokers, rightmost first, at
their sell value — until it is back under the limit.

(Named for the moneylender rather than "Le Prêteur": that is already a joker.)
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun

LOAN_AMOUNT = 30
INTEREST = 0.20  # per ante, compounding
SEIZE_AT = 90
FIRST_ANTE = 2
VISIT_CHANCE = 0.5


def visits(run: BelAtroRun) -> bool:
    """Does L'Usurier stop by the shop after the current blind?"""
    if run.ante_number < FIRST_ANTE and run.endless_ante_offset == 0:
        return False
    key = f"{run.seed}:usurier:{run.ante_number}:{run.endless_ante_offset}:{run.blind_index}"
    return random.Random(key).random() < VISIT_CHANCE


def can_borrow(run: BelAtroRun) -> bool:
    return run.loan_debt == 0 and visits(run)


def borrow(run: BelAtroRun) -> bool:
    """Take the $30 loan. False when it isn't on offer."""
    if not can_borrow(run):
        return False
    run.loan_debt = LOAN_AMOUNT
    run.loans_taken += 1
    run.economy.add_money(LOAN_AMOUNT)
    if run.recorder is not None:
        run.recorder.note_loan(LOAN_AMOUNT)
    return True


def repay(run: BelAtroRun) -> int:
    """Pay back as much of the debt as the wallet allows. Returns the amount."""
    amount = min(run.loan_debt, run.economy.money)
    if amount <= 0:
        return 0
    run.economy.spend_money(amount)
    run.loan_debt -= amount
    if run.recorder is not None:
        run.recorder.note_repay(amount)
    return amount


def accrue(run: BelAtroRun) -> list[str]:
    """New ante: the debt compounds, and past the limit L'Usurier seizes.
    Returns the lines to announce (empty when there is no debt)."""
    if run.loan_debt <= 0:
        return []
    before = run.loan_debt
    run.loan_debt = math.ceil(before * (1 + INTEREST))
    lines = [f"L'Usurier: your debt grows ${before} → ${run.loan_debt}."]
    if run.loan_debt >= SEIZE_AT:
        lines.extend(_seize(run))
    return lines


def _seize(run: BelAtroRun) -> list[str]:
    from .shop import Shop

    lines: list[str] = []
    taken = min(run.economy.money, run.loan_debt)
    if taken:
        run.economy.spend_money(taken)
        run.loan_debt -= taken
        lines.append(f"L'Usurier seizes ${taken}.")
    index = len(run.jokers) - 1
    while run.loan_debt >= SEIZE_AT and index >= 0:
        joker = run.jokers[index]
        if not joker.is_corrupted:  # even he won't touch those
            value = max(1, Shop.sell_value(joker))
            run.jokers.pop(index)
            if joker.edition.value == "neg":  # its extra slot goes with it
                run.joker_slots = max(len(run.jokers), run.joker_slots - 1)
            run.loan_debt = max(0, run.loan_debt - value)
            lines.append(f"L'Usurier seizes {joker.display_name} (${value}).")
        index -= 1
    return lines
