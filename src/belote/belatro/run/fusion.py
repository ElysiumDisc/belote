"""5.0.0 — Le Serment: joker fusion.

Two ways to fuse, both offered in the shop (the Fuse action) whenever the
player's own slots qualify:

* **Recipes** — two designated jokers become a unique fusion joker
  (`items/jokers/fusions.py`): Le Maréchal + Le Capitaine → Le Général, ...
  The recipes are a hidden page of the Collection, revealed as they're made.
* **The oath** — three copies of the same joker swear into one *Juré* copy
  (marked ✦) whose every Chips / Mult / $ payout is doubled
  (`items.base.doubled_result`). Copies are safe to own since 5.0.0
  (`Joker.state_key`), and the shop now sometimes stocks one.

A fusion keeps the best edition of its inputs (Negative excepted — its slot
was granted at purchase and stays), is corrupted if any input was, and is
worth what its inputs cost together. It takes the first input's slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..items.base import Edition, Joker, _better_edition, assign_copy_indices

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun

OATH_COPIES = 3
OATH_ID = "le_serment"  # Collection entry / discovery id of the oath itself


@dataclass(frozen=True)
class Recipe:
    id: str
    inputs: tuple[str, str]
    result: str

    # Collection shape (id / name / description), filled from the registry.
    @property
    def name(self) -> str:
        a, b = (_joker_name(i) for i in self.inputs)
        return f"{a} + {b}"

    @property
    def description(self) -> str:
        from ..items.registry import registry

        cls = registry.get_joker(self.result)
        what = cls.description if cls is not None else ""
        return f"→ {_joker_name(self.result)}. {what}"


def _joker_name(joker_id: str) -> str:
    from ..items.registry import registry

    cls = registry.get_joker(joker_id)
    return cls.name if cls is not None else joker_id


RECIPES: tuple[Recipe, ...] = (
    Recipe("recipe_general", ("le_marechal", "le_capitaine"), "le_general"),
    Recipe("recipe_tambour", ("le_sergent", "le_metronome"), "le_tambour_major"),
    Recipe("recipe_alpha", ("le_premier_sang", "le_dernier_mot"), "l_alpha_et_l_omega"),
    Recipe("recipe_couple", ("le_rebelle", "rebelote_echo"), "le_couple_royal"),
    Recipe("recipe_corsaire", ("le_contrebandier", "le_maitre_d_atout"), "le_corsaire"),
    Recipe("recipe_lucifer", ("le_traitre", "le_demon"), "lucifer"),
)


@dataclass(frozen=True)
class OathEntry:
    """The Collection row for the oath (a recipe-shaped entry)."""

    id: str = OATH_ID
    name: str = "Le Serment (3 copies)"
    description: str = (
        "Three copies of the same joker swear into one Juré copy (✦): every Chips, "
        "Mult and $ it pays is doubled, and a ×Mult's bonus too (×1.5 → ×2)."
    )


@dataclass(frozen=True)
class Fusion:
    """One fusion the player can make right now."""

    kind: str  # "recipe" | "oath"
    joker_id: str  # recipe: the result id; oath: the sworn joker's id
    recipe: Recipe | None = None

    @property
    def label(self) -> str:
        if self.recipe is not None:
            return f"{self.recipe.name} → {_joker_name(self.recipe.result)}"
        name = _joker_name(self.joker_id)
        return f"Le Serment: 3 × {name} → {name} ✦"


def _free(run: BelAtroRun, joker_id: str) -> list[Joker]:
    """The player's unsworn copies of `joker_id`, in slot order."""
    return [j for j in run.jokers if j.id == joker_id and not j.sworn]


def available_fusions(run: BelAtroRun) -> list[Fusion]:
    out: list[Fusion] = []
    for recipe in RECIPES:
        if all(_free(run, i) for i in recipe.inputs):
            out.append(Fusion("recipe", recipe.result, recipe))
    seen: set[str] = set()
    for joker in run.jokers:
        if joker.id in seen or joker.shop_excluded:
            continue
        seen.add(joker.id)
        if len(_free(run, joker.id)) >= OATH_COPIES:
            out.append(Fusion("oath", joker.id))
    return out


def fuse(run: BelAtroRun, fusion: Fusion) -> Joker | None:
    """Make `fusion` on the player's slots. Returns the new joker, or None
    when the inputs are no longer all there."""
    from ..items.registry import registry

    if fusion.recipe is not None:
        inputs = [_free(run, i)[:1] for i in fusion.recipe.inputs]
        if not all(inputs):
            return None
        parts = [found[0] for found in inputs]
        result_cls = registry.get_joker(fusion.recipe.result)
        if result_cls is None:
            return None
        joker = result_cls()
        discover: tuple[str, ...] = (fusion.recipe.id, fusion.recipe.result)
    else:
        parts = _free(run, fusion.joker_id)[:OATH_COPIES]
        if len(parts) < OATH_COPIES:
            return None
        joker = type(parts[0])()
        joker.sworn = True
        # Keep the lowest copy's namespace so run-scoped counters carry on.
        joker.copy_index = min(p.copy_index for p in parts)
        discover = (OATH_ID,)

    edition = parts[0].edition
    for part in parts[1:]:
        edition = _better_edition(edition, part.edition)
    # A Negative's extra slot was granted at purchase and stays.
    joker.edition = Edition.NONE if edition == Edition.NEGATIVE else edition
    joker.is_corrupted = joker.is_corrupted or any(p.is_corrupted for p in parts)
    joker.cost = sum(p.cost for p in parts)

    slot = run.jokers.index(parts[0])
    for part in parts:
        run.jokers.remove(part)
    run.jokers.insert(min(slot, len(run.jokers)), joker)
    assign_copy_indices([*run.jokers, *run.partner.jokers])
    if fusion.recipe is not None:
        # A recipe joker is new: fire its purchase hook (Lucifer's curse —
        # idempotent, its parents already set it).
        joker.on_purchase(run)
    if run.profile is not None:
        for item_id in discover:
            run.profile.discover(item_id)
    if run.recorder is not None:
        run.recorder.note_acquire(joker, source="le_serment")
    return joker
