"""5.0.0 — Médailles: small tokens that bend the next shop.

Earned two ways:

* **Skipping a blind.** The shop offers to skip the next Small or Big Blind
  (never a boss): no round, no payout and no shop after it — you go straight
  to the blind after — but you take that blind's medal, shown up front.
* **Feats.** Beating a blind with a capot, crushing a Boss Blind (its target
  reached by trick 4), or surviving on Capot Insurance earns one medal — at
  most one feat medal per ante.

Every medal waiting in `run.medals` is spent by the next shop's first roll
(`apply_medals`); La Cagnotte pays out the moment it's earned. Picks come
from string-seeded RNGs keyed on the run seed and the blind, so they never
disturb the run's main RNG stream and a seeded run always offers the same.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun
    from .shop import Shop


@dataclass(frozen=True)
class Medal:
    id: str
    name: str
    description: str


MEDALS: dict[str, Medal] = {
    m.id: m
    for m in (
        Medal("medal_sommelier", "Le Sommelier", "Next shop: rerolls start at $0."),
        Medal("medal_epicier", "L'Épicier", "Next shop: +2 joker offers."),
        Medal(
            "medal_antiquaire",
            "L'Antiquaire",
            "Next shop: its first joker comes Foil, Holo or Polychrome.",
        ),
        Medal("medal_tailleur", "Le Tailleur", "Next shop: a free Atelier card enhancement."),
        Medal("medal_mecene", "Le Mécène", "Next shop: its joker offers are free."),
        Medal(
            "medal_echo",
            "L'Écho",
            "Next shop: every joker offer is a copy of one you own (Le Serment!).",
        ),
        Medal("medal_cartomancien", "Le Cartomancien", "Next shop: a free Tarot card."),
        Medal("medal_cagnotte", "La Cagnotte", "Right now: double your money (max +$20)."),
    )
}
CAGNOTTE_CAP = 20
# The boss-crush feat: a Boss Blind's target reached by trick 4 of 8.
EARLY_FINISH_TRICK = 4


def _pick(run: BelAtroRun, salt: str, ante: int, offset: int, blind: int) -> str:
    rng = random.Random(f"{run.seed}:medal:{salt}:{ante}:{offset}:{blind}")
    return rng.choice(sorted(MEDALS))


def upcoming_blind(run: BelAtroRun) -> tuple[int, int, int]:
    """(ante, endless cycle, blind index) of the blind after the current one."""
    if run.blind_index < 2:
        return run.ante_number, run.endless_ante_offset, run.blind_index + 1
    if run.ante_number < 8:
        return run.ante_number + 1, run.endless_ante_offset, 0
    return run.ante_number, run.endless_ante_offset + 1, 0


def is_boss_blind(run: BelAtroRun, ante: int, blind: int) -> bool:
    """Would `blind` of `ante` roll a boss (mirrors `BelAtroGame._pick_boss`)?"""
    return (
        blind == 2
        or run.boss_rush
        or (bool(run.card_enhancements.get("boss_every_2")) and blind == 1 and ante % 2 == 0)
    )


def skip_offer(run: BelAtroRun) -> Medal | None:
    """The medal for skipping the next blind, or None when it can't be
    skipped (a boss blind, or the run is about to end)."""
    if run.run_over:
        return None
    ante, offset, blind = upcoming_blind(run)
    if run.ante_number == 8 and run.blind_index == 2 and not run.endless:
        return None  # beating this boss ends the run
    if is_boss_blind(run, ante, blind):
        return None
    return MEDALS[_pick(run, "skip", ante, offset, blind)]


def grant(run: BelAtroRun, medal_id: str) -> Medal:
    """Give the player `medal_id`: La Cagnotte pays now, the rest wait for
    the next shop."""
    medal = MEDALS[medal_id]
    run.medals_earned += 1
    if run.profile is not None:
        run.profile.discover(medal_id)
    if medal_id == "medal_cagnotte":
        run.economy.add_money(min(run.economy.money, CAGNOTTE_CAP))
    else:
        run.medals.append(medal_id)
    return medal


def feat_medal(
    run: BelAtroRun,
    *,
    capot: bool,
    reached_at: int | None,
    insured: bool,
    boss: bool = False,
) -> str | None:
    """The medal a just-settled blind earned by a feat, or None (also None
    once this ante already paid one). Called with the blind's own ante /
    blind index still current."""
    crushed = boss and reached_at is not None and reached_at <= EARLY_FINISH_TRICK
    if not (capot or crushed or insured):
        return None
    if run.feat_medal_ante == (run.ante_number, run.endless_ante_offset):
        return None
    return _pick(run, "feat", run.ante_number, run.endless_ante_offset, run.blind_index)


def pick_medal(run: BelAtroRun, salt: str) -> str:
    """A medal for the current blind, drawn under `salt` (contract rewards)."""
    return _pick(run, salt, run.ante_number, run.endless_ante_offset, run.blind_index)


def apply_medals(run: BelAtroRun, shop: Shop) -> list[Medal]:
    """Spend every waiting medal on `shop`'s first roll (before it rolls)."""
    spent = [MEDALS[m] for m in run.medals if m in MEDALS]
    run.medals.clear()
    for medal in spent:
        if medal.id == "medal_sommelier":
            shop.reroll_cost = 0
        elif medal.id == "medal_epicier":
            shop.extra_jokers += 2
        elif medal.id == "medal_antiquaire":
            shop.guaranteed_edition = True
        elif medal.id == "medal_tailleur":
            shop.free_card_mod = True
        elif medal.id == "medal_mecene":
            shop.free_jokers = True
        elif medal.id == "medal_echo":
            shop.copy_chance = 1.0
        elif medal.id == "medal_cartomancien":
            shop.free_tarot = True
    return spent
