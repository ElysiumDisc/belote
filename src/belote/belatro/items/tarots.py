from __future__ import annotations

import random
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
        run.permanent_mult += 1.0


class LeJugement(Tarot):
    id = "le_jugement"
    name = "Le Jugement"
    description = "Instantly gain a random Common Joker."

    def use(self, run: BelAtroRun, context: object) -> None:
        from .registry import registry
        avail = registry.get_available_jokers(run.profile)
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
            if len(run.consumables) < run.consumable_slots:
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
    description = "Re-applies the effect of the last Tarot or Planet card used."

    def use(self, run: BelAtroRun, context: object) -> None:
        from .registry import registry

        last_id = run.last_consumable_id
        # Re-apply the most recently used consumable. We deliberately leave
        # `last_consumable_id` pointing at that item so a second LeFou keeps
        # copying the same source rather than copying itself.
        if last_id and last_id != self.id:
            tarot_cls = registry.tarots.get(last_id)
            planet_cls = registry.planets.get(last_id)
            if tarot_cls is not None:
                tarot_cls().use(run, context)
                return
            if planet_cls is not None:
                planet_cls().use(run)
                return
        # Fallback if we have no record of a prior consumable (run just
        # started): grant a random tarot to the consumables tray.
        tarots = [t for t in registry.tarots.values() if t is not type(self)]
        if tarots and len(run.consumables) < run.consumable_slots:
            run.consumables.append(random.choice(tarots)())


class LaForce(Tarot):
    id = "la_force"
    name = "La Force"
    description = "Immediately gain +20 Chips permanently."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.permanent_chips += 20


class LeSoleil(Tarot):
    id = "le_soleil"
    name = "Le Soleil"
    description = "Immediately earn $10."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.economy.money += 10


class LaMaisonDieu(Tarot):
    """Wipes one active boss modifier for the next round."""

    id = "la_maison_dieu"
    name = "La Maison-Dieu"
    description = "Disable the active boss modifier for one round."

    def use(self, run: BelAtroRun, context: object) -> None:
        # The flag is read by _play_blind to skip boss application this blind.
        run.card_enhancements["disable_next_boss"] = True


class LeDiable(Tarot):
    """Forces the partner to always over-trump for one round."""

    id = "le_diable"
    name = "Le Diable"
    description = "Partner always over-cuts the trick (sometimes great, sometimes ruinous) for one round."

    def use(self, run: BelAtroRun, context: object) -> None:
        run.card_enhancements["partner_overcut_round"] = True
