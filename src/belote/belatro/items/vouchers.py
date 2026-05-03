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
        # Placeholder for round-end bonus logic
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
    description = "Shop always stocks at least one Tarot card. Permanent."

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
    description = "Know your AI partner's bidding tendency before each round. Permanent."

    def apply(self, run: BelAtroRun) -> None:
        pass


class LesCartesDorees(Voucher):
    id = "les_cartes_dorees"
    name = "Les Cartes Dorées"
    description = "Permanently gain +5% interest rate."

    def apply(self, run: BelAtroRun) -> None:
        # Assuming interest_rate is handled in economy
        pass


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
