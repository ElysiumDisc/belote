from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Voucher

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class LaTelescope(Voucher):
    id = "la_telescope"
    name = "La Télescope"
    description = "See the top 3 cards of your deal before committing to a bid."

    def apply(self, run: BelAtroRun) -> None:
        pass


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
    description = "Shop always stocks at least one Tarot card."

    def apply(self, run: BelAtroRun) -> None:
        pass


class LaDoubleDonne(Voucher):
    id = "la_double_donne"
    name = "La Double Donne"
    description = "Gain one extra Joker slot (default 5 → 6)."

    def apply(self, run: BelAtroRun) -> None:
        run.joker_slots += 1


class LEncyclopedie(Voucher):
    id = "lencyclopedie"
    name = "L'Encyclopédie"
    description = "Know your AI partner's bidding tendency before each round."

    def apply(self, run: BelAtroRun) -> None:
        pass


class LesCartesDorees(Voucher):
    id = "les_cartes_dorees"
    name = "Les Cartes Dorées"
    description = "Gold Seal cards earn $5 per trick win instead of $3."

    def apply(self, run: BelAtroRun) -> None:
        pass


class LeCouteau(Voucher):
    id = "le_couteau"
    name = "Le Couteau"
    description = "Can destroy any card in your deck during the Shop phase for $2 refund."

    def apply(self, run: BelAtroRun) -> None:
        pass


class LaBalance(Voucher):
    id = "la_balance"
    name = "La Balance"
    description = "If both teams tie in card points, your team wins the round automatically."

    def apply(self, run: BelAtroRun) -> None:
        pass


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
