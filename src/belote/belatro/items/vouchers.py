from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Voucher

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class LaTelescope(Voucher):
    id = "la_telescope"
    name = "La Télescope"
    description = "Permanent: Earn +$1 bonus after each round."

    def apply(self, run: BelAtroRun) -> None:
        run.economy.bonus_per_round += 1


class LaVoute(Voucher):
    id = "la_voute"
    name = "La Voûte"
    description = "Earn $1 per $5 held at round end, max $5/round."

    def apply(self, run: BelAtroRun) -> None:
        run.economy.interest_rate = 1
        run.economy.max_interest = 5


class LeGrimoire(Voucher):
    id = "le_grimoire"
    name = "Le Grimoire"
    description = "Shop always stocks at least one Tarot card. Permanent."

    def apply(self, run: BelAtroRun) -> None:
        run.guarantee_tarot_in_shop = True


class LaDoubleDonne(Voucher):
    id = "la_double_donne"
    name = "La Double Donne"
    description = "Gain one extra Joker slot (default 5 → 6)."

    def apply(self, run: BelAtroRun) -> None:
        run.joker_slots += 1


class LEncyclopedie(Voucher):
    id = "lencyclopedie"
    name = "L'Encyclopédie"
    description = "Know your AI partner's bidding tendency before each round. Permanent."

    def apply(self, run: BelAtroRun) -> None:
        run.show_partner_bid_tendency = True


class LesCartesDorees(Voucher):
    id = "les_cartes_dorees"
    name = "Les Cartes Dorées"
    description = "Permanently gain +1 interest rate and +5 interest cap."

    def apply(self, run: BelAtroRun) -> None:
        run.economy.interest_rate += 1
        run.economy.max_interest += 5


class LeCouteau(Voucher):
    id = "le_couteau"
    name = "Le Couteau"
    description = "Gain one extra consumable slot."

    def apply(self, run: BelAtroRun) -> None:
        run.consumable_slots += 1


class LaBalance(Voucher):
    id = "la_balance"
    name = "La Balance"
    description = "If both teams tie in card points, your team wins the round automatically."

    def apply(self, run: BelAtroRun) -> None:
        run.tie_breaks_for_taker = True


class LaSurcoinche(Voucher):
    id = "la_surcoinche"
    name = "La Surcoinche"
    description = "Unlocks the Surcoinche contract."
    is_unlockable = True

    def apply(self, run: BelAtroRun) -> None:
        pass


class LeCarnet(Voucher):
    id = "le_carnet"
    name = "Le Carnet"
    description = "You see partner's full hand. +1 Mult each time YOU (South) win a trick."

    def apply(self, run: BelAtroRun) -> None:
        run.show_north_hand = True


class CapotInsurance(Voucher):
    id = "capot_insurance"
    name = "Assurance Capot"
    description = "One-shot: if you chute next round, the cash penalty is halved."
    cost = 8

    def apply(self, run: BelAtroRun) -> None:
        run.capot_insurance = True


class TierceForge(Voucher):
    id = "tierce_forge"
    name = "Forge des Annonces"
    description = "Spend 3 Tierce charges in the shop to level up a Planet contract for free."
    cost = 6

    def apply(self, run: BelAtroRun) -> None:
        # The activation logic lives in the shop UI; flag stays unused at apply time.
        # Just having the voucher equipped enables the option in shop interactions.
        pass
