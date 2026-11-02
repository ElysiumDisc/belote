"""5.0.0 — Café-text interstitials: your partner's side of the story.

`personality.py` and `TrustTrack` already model how the partner feels; these
beats let them say it. After each round `next_beat` looks at what just
happened (`RoundFacts` — chiefly the trust transition) and returns the first
beat that matches and hasn't fired this run. At most one per round, each at
most once per run (`BelAtroRun.story_seen`).

Every beat grants a small one-shot buff (`StoryBuff`): money or trust lands
at once; chips / Mult / ×Mult wait in `run.story_buff` and are spent by the
next round (`ScoreAccumulator.story_buff`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


@dataclass(frozen=True)
class StoryBuff:
    chips: int = 0
    mult: float = 0.0
    times_mult: float = 0.0
    money: int = 0
    trust: int = 0

    def label(self) -> str:
        parts: list[str] = []
        if self.chips:
            parts.append(f"+{self.chips} chips next round")
        if self.mult:
            parts.append(f"+{self.mult:g} Mult next round")
        if self.times_mult:
            parts.append(f"×{self.times_mult:g} Mult next round")
        if self.money:
            parts.append(f"+${self.money}")
        if self.trust:
            parts.append(f"+{self.trust} trust")
        return ", ".join(parts)


@dataclass(frozen=True)
class RoundFacts:
    """What the round that just ended did, as the beats see it."""

    trust_before: int
    trust_after: int
    won: bool
    ns_capot: bool = False
    ns_chute: bool = False
    boss_beaten: bool = False
    sabotaged: bool = False  # the partner threw a trick (Le Traître & co.)
    coinche_made: bool = False  # NS made a coinched contract
    insured: bool = False  # survived on Capot Insurance
    ante: int = 1
    first_round_of_ante: bool = False


@dataclass(frozen=True)
class StoryBeat:
    id: str
    title: str
    lines: tuple[str, ...]  # "{partner}" is replaced by the partner's name
    buff: StoryBuff = field(default_factory=StoryBuff)

    def text(self, partner: str) -> list[str]:
        return [line.replace("{partner}", partner) for line in self.lines]


def _crossed_up(f: RoundFacts, threshold: int) -> bool:
    return f.trust_before < threshold <= f.trust_after


def _crossed_down(f: RoundFacts, threshold: int) -> bool:
    return f.trust_after <= threshold < f.trust_before


# (beat, trigger) in priority order — the first unseen match fires.
_BEATS: tuple[tuple[StoryBeat, Callable[[RoundFacts], bool]], ...] = (
    (
        StoryBeat(
            "la_trahison",
            "La Trahison",
            (
                "{partner} won't meet your eyes over the zinc.",
                '"That trick… I threw it. You knew I would, didn\'t you?"',
                '"Let me make it up to you."',
            ),
            StoryBuff(chips=20),
        ),
        lambda f: f.sabotaged,
    ),
    (
        StoryBeat(
            "les_retrouvailles",
            "Les Retrouvailles",
            (
                "A capot. Eight tricks, not one dropped.",
                "{partner} laughs for the first time in days and orders two pastis.",
                '"Alright. We\'re a team again."',
            ),
            StoryBuff(times_mult=1.25),
        ),
        lambda f: f.ns_capot and f.trust_before <= 4,
    ),
    (
        StoryBeat(
            "le_premier_capot",
            "Le Premier Capot",
            (
                "The whole café turns round. Every trick, ours.",
                "{partner} slaps the table hard enough to spill the coffee.",
                '"Drinks are on the house, apparently."',
            ),
            StoryBuff(money=5),
        ),
        lambda f: f.ns_capot,
    ),
    (
        StoryBeat(
            "les_jumeaux",
            "Les Jumeaux",
            (
                "You don't need to signal any more. {partner} already knows.",
                "Someone at the next table asks if you two are related.",
            ),
            StoryBuff(times_mult=1.5),
        ),
        lambda f: _crossed_up(f, 10),
    ),
    (
        StoryBeat(
            "le_sauvetage",
            "Le Sauvetage",
            (
                "The insurance paid. Barely.",
                "{partner}, shakily: \"We're still in it. Don't do that to me again.\"",
            ),
            StoryBuff(chips=20),
        ),
        lambda f: f.insured,
    ),
    (
        StoryBeat(
            "le_premier_boss",
            "Le Premier Boss",
            (
                "The boss blind is behind you. {partner} exhales.",
                '"I thought that one had us. I really did."',
            ),
            StoryBuff(chips=25),
        ),
        lambda f: f.boss_beaten,
    ),
    (
        StoryBeat(
            "l_elan",
            "L'Élan",
            (
                "{partner} is leaning forward now, counting trumps out loud.",
                '"Keep feeding me the lead. I\'ve got this."',
            ),
            StoryBuff(mult=2.0),
        ),
        lambda f: _crossed_up(f, 7),
    ),
    (
        StoryBeat(
            "la_coinche",
            "La Coinche",
            (
                "They coinched you. You made it anyway.",
                '{partner} grins at the opponents: "Encore une?"',
            ),
            StoryBuff(mult=1.0),
        ),
        lambda f: f.coinche_made,
    ),
    (
        StoryBeat(
            "la_chute",
            "La Chute",
            (
                "Down. The contract fell, and the café went quiet.",
                '{partner} pushes a coin across the table. "Next one\'s on me."',
            ),
            StoryBuff(money=3),
        ),
        lambda f: f.ns_chute,
    ),
    (
        StoryBeat(
            "la_bouderie",
            "La Bouderie",
            (
                "{partner} is sulking behind the newspaper.",
                "You order them a café crème. A small truce.",
            ),
            StoryBuff(trust=1),
        ),
        lambda f: _crossed_down(f, 4),
    ),
    (
        StoryBeat(
            "au_bord_du_divorce",
            "Au Bord du Divorce",
            (
                "{partner} has their coat on. Their hand is on the door.",
                "You say the one thing that makes them sit back down.",
            ),
            StoryBuff(trust=2),
        ),
        lambda f: _crossed_down(f, 2),
    ),
    (
        StoryBeat(
            "minuit_au_cafe",
            "Minuit au Café",
            (
                "Ante 6. The chairs are on the tables; the patron lets you stay.",
                '{partner}, quietly: "Whatever happens — this was a good run."',
            ),
            StoryBuff(money=4),
        ),
        lambda f: f.first_round_of_ante and f.ante == 6,
    ),
)

BEATS: dict[str, StoryBeat] = {beat.id: beat for beat, _ in _BEATS}


def next_beat(run: BelAtroRun, facts: RoundFacts) -> StoryBeat | None:
    """The first unseen beat `facts` triggers, or None."""
    for beat, trigger in _BEATS:
        if beat.id in run.story_seen:
            continue
        if trigger(facts):
            return beat
    return None


def grant(run: BelAtroRun, beat: StoryBeat) -> None:
    """Mark `beat` seen and grant its buff."""
    run.story_seen.add(beat.id)
    buff = beat.buff
    if buff.money:
        run.economy.add_money(buff.money)
    if buff.trust:
        trust = run.partner.trust
        trust.value = min(10, trust.value + buff.trust)
    pending = run.story_buff
    if buff.chips:
        pending["chips"] = pending.get("chips", 0) + buff.chips
    if buff.mult:
        pending["mult"] = pending.get("mult", 0.0) + buff.mult
    if buff.times_mult:
        pending["times_mult"] = pending.get("times_mult", 1.0) * buff.times_mult
