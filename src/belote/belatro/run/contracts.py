"""5.0.0 — Contrat Capot & Grand Chelem: Belote's dream results as blinds.

From Ante 2, some antes mark their Big Blind as a **contract blind** (seeded:
the same run always gets the same ones). The blind plays as normal unless,
once your team holds the contract and you've seen your hand, you *declare*:

* **Contrat Capot** — your team takes all 8 tricks. Made: the blind is won
  whatever the score, +$10 and a Médaille. Missed: the blind is lost.
* **Grand Chelem** (Ante 5+) — the capot *and* you (South) personally win at
  least 5 of the 8 tricks. Made: the blind is won, +$25, +1 joker slot and
  two Médailles. Missed: the blind is lost.

A lost contract ends the run like any failed blind — unless Capot Insurance
(the Phase 2.1 one-shot) covers it, which is what it was always named for.
The declaration is offered by `round_driver` through
`RoundUICallbacks.prompt_special_contract`; it never appears on a boss blind,
in Boss Rush, or when the opponents took the contract.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from belote.game import GameState

    from ..core.run_state import BelAtroRun

CAPOT = "capot"
CHELEM = "chelem"
CONTRACT_CHANCE = 0.35  # per ante, from Ante 2
CHELEM_ANTE = 5
CHELEM_SHARE = 0.4  # of contract blinds from Ante 5 on
CHELEM_SOUTH_TRICKS = 5
# joker_state keys: the offer (set by BelAtroGame._round_flags) and the
# declaration (set by round_driver when the player accepts).
OFFER_KEY = "special_contract_offer"
DECLARED_KEY = "special_contract_declared"


@dataclass(frozen=True)
class ContractInfo:
    kind: str
    name: str
    rule: str
    reward: str
    money: int
    medals: int
    extra_slot: bool


CONTRACTS: dict[str, ContractInfo] = {
    CAPOT: ContractInfo(
        CAPOT,
        "Contrat Capot",
        "your team takes all 8 tricks",
        "blind won outright, +$10 and a Médaille",
        money=10,
        medals=1,
        extra_slot=False,
    ),
    CHELEM: ContractInfo(
        CHELEM,
        "Grand Chelem",
        f"all 8 tricks, and you win at least {CHELEM_SOUTH_TRICKS} of them yourself",
        "blind won outright, +$25, +1 joker slot and two Médailles",
        money=25,
        medals=2,
        extra_slot=True,
    ),
}


def contract_blind(run: BelAtroRun) -> str | None:
    """The contract the current blind offers (CAPOT / CHELEM), or None."""
    return contract_for(run, run.ante_number, run.endless_ante_offset, run.blind_index)


def contract_for(run: BelAtroRun, ante: int, offset: int, blind: int) -> str | None:
    """The contract blind `blind` of `ante` (endless cycle `offset`) offers —
    the shop previews the next blind with it."""
    from .medals import is_boss_blind

    if blind != 1 or ante < 2 or run.boss_rush or is_boss_blind(run, ante, 1):
        return None
    rng = random.Random(f"{run.seed}:contract:{ante}:{offset}")
    if rng.random() >= CONTRACT_CHANCE:
        return None
    chelem = ante >= CHELEM_ANTE and rng.random() < CHELEM_SHARE
    return CHELEM if chelem else CAPOT


def contract_made(kind: str, state: GameState) -> bool:
    """Did the finished round make `kind`? Uses the resolved trick winners
    (La Rupture / L'Anarchie aware), like `score_round`."""
    from belote.deck import Contract
    from belote.game import Seat, compute_trick_winners, team_of

    if len(state.completed_tricks) != 8:
        return False
    winners = compute_trick_winners(state, state.trump, state.contract == Contract.SANS_ATOUT)
    if any(w is None or team_of(w) != 0 for w in winners):
        return False
    if kind == CHELEM:
        return sum(1 for w in winners if w == Seat.SOUTH) >= CHELEM_SOUTH_TRICKS
    return True
