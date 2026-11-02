"""5.0.0 — L'Atelier: per-card enhancements and seals.

Every one of the 32 cards can carry one **enhancement** and one **seal**,
bought from the shop's Atelier offer and kept for the rest of the run
(`BelAtroRun.card_mods`, keyed by `card_key`).

The trick-taking twist: they trigger on **capture**, not on play. Whoever
held the card, it pays out when *your team* wins the trick it is in — so an
enhanced card in an opponent's hand is a prize to take, and one in yours is a
card you want to see your partner win.

Enhancements
  Verre   — the card's points count twice; 1 in 4 it shatters: the trick
            scores 0 chips and the Verre is gone.
  Acier   — your trick jokers trigger again on the trick it is captured in.
  Chance  — a random reward when captured (chips, Mult, $ or ×Mult).
Seals
  Rouge   — +2 Mult when it is the card that takes the trick for your team.
  Bleu    — captured during the round: your round-end jokers trigger again.
  Or      — +$1 when your team captures it (paid when you beat the blind).

Scoring lives in `ScoreAccumulator._trick_card_mods`; jokers react through
the `on_card_captured` hook (`CardCapturedEvent`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from belote.deck import Card, Rank, Suit

ENHANCEMENTS: dict[str, tuple[str, str]] = {
    # id: (name, description)
    "verre": (
        "Verre",
        "Captured: its points count twice. 1 in 4 it shatters — the trick scores 0.",
    ),
    "acier": ("Acier", "Captured: your trick jokers trigger again on that trick."),
    "chance": ("Chance", "Captured: a random reward — chips, Mult, $ or ×Mult."),
}
SEALS: dict[str, tuple[str, str]] = {
    "rouge": ("Sceau Rouge", "+2 Mult when it takes a trick for your team."),
    "bleu": ("Sceau Bleu", "Captured during the round: round-end jokers trigger again."),
    "or": ("Sceau d'Or", "+$1 when your team captures it (paid when the blind is beaten)."),
}
# Shop price per mod (the Atelier offer).
MOD_COST: dict[str, int] = {
    "verre": 4,
    "acier": 6,
    "chance": 4,
    "rouge": 5,
    "bleu": 6,
    "or": 4,
}
# One-letter badges (inventory / HUD lists).
MOD_BADGE: dict[str, str] = {
    "verre": "V",
    "acier": "A",
    "chance": "?",
    "rouge": "r",
    "bleu": "b",
    "or": "$",
}

VERRE_SHATTER_CHANCE = 0.25
ROUGE_MULT = 2.0


@dataclass
class CardMod:
    """What one card carries. Both slots may be empty (then it's dropped)."""

    enhancement: str | None = None
    seal: str | None = None

    def is_empty(self) -> bool:
        return self.enhancement is None and self.seal is None

    def label(self) -> str:
        parts = [ENHANCEMENTS[self.enhancement][0]] if self.enhancement else []
        if self.seal:
            parts.append(SEALS[self.seal][0])
        return " + ".join(parts)


def card_key(card: Card) -> str:
    """Stable key of a card in `card_mods` (e.g. ``"ACE_HEARTS"``)."""
    return f"{card.rank.name}_{card.suit.name}"


def card_from_key(key: str) -> Card | None:
    rank_name, _, suit_name = key.partition("_")
    try:
        return Card(Suit[suit_name], Rank[rank_name])
    except KeyError:
        return None


def mod_kind(mod_id: str) -> str:
    """ "enhancement" or "seal"."""
    return "enhancement" if mod_id in ENHANCEMENTS else "seal"


def mod_name(mod_id: str) -> str:
    return (ENHANCEMENTS.get(mod_id) or SEALS[mod_id])[0]


def mod_description(mod_id: str) -> str:
    return (ENHANCEMENTS.get(mod_id) or SEALS[mod_id])[1]


def apply_mod(mods: dict[str, CardMod], card: Card, mod_id: str) -> None:
    """Put `mod_id` on `card` (replacing whatever was in that slot)."""
    entry = mods.setdefault(card_key(card), CardMod())
    if mod_kind(mod_id) == "enhancement":
        entry.enhancement = mod_id
    else:
        entry.seal = mod_id


def remove_enhancement(mods: dict[str, CardMod], key: str) -> None:
    entry = mods.get(key)
    if entry is None:
        return
    entry.enhancement = None
    if entry.is_empty():
        del mods[key]


def mod_rng(seed: int, trick_number: int, key: str, salt: str = "") -> random.Random:
    """Deterministic per-capture RNG (string seeds hash with SHA-512, so this
    is stable across processes — unlike `hash()`). Seeded runs replay."""
    return random.Random(f"{seed}:{trick_number}:{key}:{salt}")


@dataclass(frozen=True)
class CardModOffer:
    """The shop's Atelier offer: `mod_id` applied to `card` on purchase."""

    card: Card
    mod_id: str
    cost: int

    @property
    def id(self) -> str:
        return f"atelier_{self.mod_id}"

    @property
    def name(self) -> str:
        return mod_name(self.mod_id)

    @property
    def description(self) -> str:
        return f"L'Atelier: {self.name} on the {self.card!r}. {mod_description(self.mod_id)}"
