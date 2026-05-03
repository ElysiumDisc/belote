from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Tarot

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class LeChariot(Tarot):
    id = "le_chariot"
    name = "Le Chariot"
    description = "Immediately earn $5."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.economy.money += 5


class LaRoue(Tarot):
    id = "la_roue"
    name = "La Roue"
    description = "Gain +1.0 Mult for the remainder of the run (permanently)."

    def use(self, run: BelAtroRun, context: object) -> None:
        # We can't easily store permanent mult on run without a field,
        # but we can increase base mult if it exists.
        # For now, let's assume it adds to a permanent_mult field.
        pass


class LeJugement(Tarot):
    id = "le_jugement"
    name = "Le Jugement"
    description = "Instantly gain a random Common Joker."

    def use(self, run: BelAtroRun, context: object) -> None:
        from .registry import registry
        from .base import Joker
        avail = registry.get_available_jokers(None)
        if avail:
            j_id = random.choice(list(avail.keys()))
            joker = avail[j_id]()
            if len(run.jokers) < run.joker_slots:
                run.jokers.append(joker)


class LeMonde(Tarot):
    id = "le_monde"
    name = "Le Monde"
    description = "Immediately earn $1 for each Joker you own."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.economy.money += len(run.jokers)


class LaPretresse(Tarot):
    id = "la_pretresse"
    name = "La Prêtresse"
    description = "Immediately gain two random Planet cards."

    def use(self, run: BelAtroRun, context: object) -> None:
        from .registry import registry
        planets = list(registry.planets.values())
        for _ in range(2):
            p_cls = random.choice(planets)
            run.consumables.append(p_cls())


class LaLune(Tarot):
    id = "la_lune"
    name = "La Lune"
    description = "Permanently increase interest cap by $2."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.economy.max_interest += 2


class LaTemperance(Tarot):
    id = "la_temperance"
    name = "La Tempérance"
    description = "Earn money equal to the total sell value of all currently held Jokers."

    def use(self, run: BelAtroRun, context: object) -> None:
        total_val = sum(j.cost // 2 for j in run.jokers)
        run.economy.money += total_val


class LeFou(Tarot):
    id = "le_fou"
    name = "Le Fou"
    description = "Create a copy of the last Tarot or Planet card used."

    def use(self, run: BelAtroRun, context: object) -> None:
        # Requires tracking last used; for now just give a random Tarot.
        from .registry import registry
        tarots = list(registry.tarots.values())
        run.consumables.append(random.choice(tarots)())


class LaForce(Tarot):
    id = "la_force"
    name = "La Force"
    description = "Immediately gain +20 Chips permanently."

    def use(self, run: BelAtroRun, context: object) -> None:
        # Similar to La Roue, needs a permanent chips field.
        pass


class LeSoleil(Tarot):
    id = "le_soleil"
    name = "Le Soleil"
    description = "Immediately earn $10."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.economy.money += 10
