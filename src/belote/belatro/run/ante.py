from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ante:
    number: int
    name: str
    target: int


def calculate_target(ante: int, blind_index: int) -> int:
    """
    Scaling formula:
    Base for Ante 1 is 100.
    Small Blind (0): x1
    Big Blind (1): x1.5
    Boss Blind (2): x2
    Each Ante scales target by x1.5
    """
    base = 100
    ante_multiplier = 1.5 ** (ante - 1)
    blind_multiplier = [1.0, 1.5, 2.0][blind_index]
    return int(base * ante_multiplier * blind_multiplier)


# 8 Antes x 3 Blinds each
ANTE_TABLE: list[list[Ante]] = [
    [
        Ante(
            number=a,
            name=["Small Blind", "Big Blind", "Boss Blind"][b],
            target=calculate_target(a, b),
        )
        for b in range(3)
    ]
    for a in range(1, 9)
]
