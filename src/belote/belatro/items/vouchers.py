from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Voucher

if TYPE_CHECKING:
    from ..core.run_state import BelAtroRun


class LaTelescope(Voucher):
    id = "la_telescope"
    name = "La Télescope"
    description = "Permanent: Earn +$1 bonus after each round."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.economy.bonus_per_round += 1


class LaVoute(Voucher):
    id = "la_voute"
    name = "La Voûte"
    description = "Earn $1 per $5 held at round end, max $5/round."

    def _apply_once(self, run: BelAtroRun) -> None:
        # Use max() rather than `=` so LaVoute can't wipe additive bonuses
        # already granted by LesCartesDorees (which is `+=` against the same
        # fields). LaVoute defines a floor of (rate=1, cap=5).
        run.economy.interest_rate = max(run.economy.interest_rate, 1)
        run.economy.max_interest = max(run.economy.max_interest, 5)


class LeGrimoire(Voucher):
    id = "le_grimoire"
    name = "Le Grimoire"
    description = "Shop always stocks at least one Tarot card. Permanent."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.guarantee_tarot_in_shop = True


class LaDoubleDonne(Voucher):
    id = "la_double_donne"
    name = "La Double Donne"
    description = "Gain one extra Joker slot (default 5 → 6)."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.joker_slots += 1


class LEncyclopedie(Voucher):
    id = "lencyclopedie"
    name = "L'Encyclopédie"
    description = "Know your AI partner's bidding tendency before each round. Permanent."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.show_partner_bid_tendency = True


class LesCartesDorees(Voucher):
    id = "les_cartes_dorees"
    name = "Les Cartes Dorées"
    description = "Permanently gain +1 interest rate and +5 interest cap."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.economy.interest_rate += 1
        run.economy.max_interest += 5


class LeCouteau(Voucher):
    id = "le_couteau"
    name = "Le Couteau"
    description = "Gain one extra consumable slot."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.consumable_slots += 1


class LaBalance(Voucher):
    id = "la_balance"
    name = "La Balance"
    description = "If both teams tie in card points, your team wins the round automatically."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.tie_breaks_for_taker = True


class LaSurcoinche(Voucher):
    id = "la_surcoinche"
    name = "La Surcoinche"
    description = "Unlocks the Surcoinche contract (AI may surcoinche when you coinche)."
    is_unlockable = True

    def _apply_once(self, run: BelAtroRun) -> None:
        run.surcoinche_unlocked = True


class LeCarnet(Voucher):
    id = "le_carnet"
    name = "Le Carnet"
    description = "You see partner's full hand. +1 Mult each time YOU (South) win a trick."

    def _apply_once(self, run: BelAtroRun) -> None:
        run.show_north_hand = True


class CapotInsurance(Voucher):
    id = "capot_insurance"
    name = "Assurance Capot"
    description = "One-shot: if you chute next round, the cash penalty is halved."
    cost = 8

    def _apply_once(self, run: BelAtroRun) -> None:
        run.capot_insurance = True


class TierceForge(Voucher):
    id = "tierce_forge"
    name = "Forge des Annonces"
    description = "Spend 3 Tierce charges in the shop to level up a Planet contract for free."
    cost = 6

    def _apply_once(self, run: BelAtroRun) -> None:
        # No-op at apply time. Owning the voucher enables `run.forge_tierce`
        # which the shop UI calls when the player chooses to spend charges.
        pass


def forge_tierce(run: BelAtroRun, planet_id: str) -> bool:
    """Spend 3 Tierce charges to apply a Planet's level-up reward.

    Returns True if the forge succeeded. Caller (shop UI) is responsible for
    verifying the TierceForge voucher is actually owned before invoking.
    """
    from ..items.registry import registry

    if run.tierce_charges < 3:
        return False
    planet_cls = registry.get_planet(planet_id)
    if planet_cls is None:
        return False
    planet = planet_cls()
    run.tierce_charges -= 3
    # Delegate to Planet.use() so overlapping numeric levels are summed
    # rather than overwritten — matches the regular planet level-up path
    # (base.py: Planet.use). Previously this used dict ** merge which
    # silently dropped earlier levels.
    planet.use(run)
    return True
