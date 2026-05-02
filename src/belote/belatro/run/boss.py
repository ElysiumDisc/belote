from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.modifier_patch import PatchedGameState


class BossModifier(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def apply(self, state: PatchedGameState) -> PatchedGameState:
        """Patch the GameState before the round begins."""
        ...


# ── Standard Boss Blinds (11) ──────────────────────────────────────────────


class LaGrandeMuette(BossModifier):
    id = "la_grande_muette"
    name = "La Grande Muette"
    description = "Belote/Rebelote cannot be announced. Flat 20 points removed."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_no_belote", True)
        return state


class LAnarchie(BossModifier):
    id = "l_anarchie"
    name = "L'Anarchie"
    description = "Trump changes to a random suit after every 2 tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_dynamic_trump", True)
        return state


class LeRoiMort(BossModifier):
    id = "le_roi_mort"
    name = "Le Roi Mort"
    description = "All Kings are worth 0 card points this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_kings_zero", True)
        return state


class LaMalediction(BossModifier):
    id = "la_malediction"
    name = "La Malédiction"
    description = "The team winning MORE tricks scores ZERO this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_invert_scoring", True)
        return state


class LAvocat(BossModifier):
    id = "l_avocat"
    name = "L'Avocat"
    description = "You must Coinche your own bid — target doubles, payout triples."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_auto_coinche", True)
        return state


class LeDeluge(BossModifier):
    id = "le_deluge"
    name = "Le Déluge"
    description = "All 7s and 8s become trump regardless of declared suit."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_seven_eight_trump", True)
        return state


class LaReineNoire(BossModifier):
    id = "la_reine_noire"
    name = "La Reine Noire"
    description = "Whoever captures the Queen of Spades subtracts 25 points."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_queen_spades_penalty", True)
        return state


class LeBrouillard(BossModifier):
    id = "le_brouillard"
    name = "Le Brouillard"
    description = "Score HUD is hidden until the round ends."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_hide_hud", True)
        return state


class LesClubsBannis(BossModifier):
    id = "les_clubs_bannis"
    name = "Les Clubs Bannis"
    description = "Clubs cannot be called as trump. Club tricks score 0."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_ban_clubs", True)
        return state


class LeZeroFinal(BossModifier):
    id = "le_zero_final"
    name = "Le Zéro Final"
    description = "The last trick is worth 0 points. Dix de Der is negated."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_no_dix_de_der", True)
        return state


class LesDixMaudits(BossModifier):
    id = "les_dix_maudits"
    name = "Les Dix Maudits"
    description = "All 10s are treated as 7s (0 point value) for this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_tens_zero", True)
        return state


# ── Partner Boss Blinds (6) ────────────────────────────────────────────────


class LaRupture(BossModifier):
    id = "la_rupture"
    name = "La Rupture"
    description = "You and partner cannot win consecutive tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_no_consecutive_team_wins", True)
        return state


class LeFantomePartenaire(BossModifier):
    id = "le_fantome_partenaire"
    name = "Le Fantôme Partenaire"
    description = "Partner's hand is invisible to you for the entire round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_hide_partner_hand", True)
        return state


class LAgentDoubleBoss(BossModifier):
    id = "l_agent_double_boss"
    name = "L'Agent Double"
    description = "Partner plays optimally for the opponents for a random 3 tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_agent_double_active", True)
        return state


class LaSolitude(BossModifier):
    id = "la_solitude"
    name = "La Solitude"
    description = "Partner passes every bid. You must bid alone."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_partner_forced_pass", True)
        return state


class LeDivorce(BossModifier):
    id = "le_divorce"
    name = "Le Divorce"
    description = "Trust track is locked at 0 for this round. No Trust bonuses."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_lock_trust_zero", True)
        return state


class LaCompetition(BossModifier):
    id = "la_competition"
    name = "La Compétition"
    description = "You and partner score separately. Only higher total counts."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_separate_scoring", True)
        return state


# ── Registry ───────────────────────────────────────────────────────────────

ALL_BOSS_MODIFIERS: list[type[BossModifier]] = [
    LaGrandeMuette,
    LAnarchie,
    LeRoiMort,
    LaMalediction,
    LAvocat,
    LeDeluge,
    LaReineNoire,
    LeBrouillard,
    LesClubsBannis,
    LeZeroFinal,
    LesDixMaudits,
    LaRupture,
    LeFantomePartenaire,
    LAgentDoubleBoss,
    LaSolitude,
    LeDivorce,
    LaCompetition,
]
