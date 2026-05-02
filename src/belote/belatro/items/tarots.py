from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Tarot

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class LeChariot(Tarot):
    id = "le_chariot"
    name = "Le Chariot"
    description = "Immediately steal the current trick (usable only when leading)."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass  # Implementation depends on round driver hooks


class LaRoue(Tarot):
    id = "la_roue"
    name = "La Roue"
    description = "Randomly swap the declared trump suit to a new one mid-round."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LeJugement(Tarot):
    id = "le_jugement"
    name = "Le Jugement"
    description = "Resurrect a destroyed Joker from the discard pile."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LeMonde(Tarot):
    id = "le_monde"
    name = "Le Monde"
    description = "Double all declaration points this round only."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LaPretresse(Tarot):
    id = "la_pretresse"
    name = "La Prêtresse"
    description = "Secretly view one opponent's full hand for 3 seconds."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LaLune(Tarot):
    id = "la_lune"
    name = "La Lune"
    description = "For the next trick only, opponents play blind."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LaTemperance(Tarot):
    id = "la_temperance"
    name = "La Tempérance"
    description = "Permanently destroy one card from your deck."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LeFou(Tarot):
    id = "le_fou"
    name = "Le Fou"
    description = "Add a second copy of a random card already in your deck."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LaForce(Tarot):
    id = "la_force"
    name = "La Force"
    description = "Partner's tricks count as yours for scoring this round."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass


class LeSoleil(Tarot):
    id = "le_soleil"
    name = "Le Soleil"
    description = "Next trick you win, earn $3 directly."

    def use(self, run: BelAtroRun, context: object) -> None:
        pass
