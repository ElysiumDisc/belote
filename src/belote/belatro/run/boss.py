from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from belote.game import BossModifiers

    from ..engine.modifier_patch import PatchedGameState


class BossModifier(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def apply(self, state: PatchedGameState) -> PatchedGameState:
        """Patch the GameState before the round begins."""
        ...

    def flags(self) -> BossModifiers:
        """Return the BossModifiers dataclass produced by this boss's apply().

        Useful for pre-round setup that needs to react to flags without driving
        a full round. Independent of the live GameState — uses a stub.
        """
        from belote.game import GameState, new_game

        from ..engine.modifier_patch import PatchedGameState

        stub: GameState = new_game()
        proxy = PatchedGameState(stub)
        self.apply(proxy)
        patches = object.__getattribute__(proxy, "_patches")
        return patches.get("boss_modifiers", stub.boss_modifiers)


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


class BetrayalArc(BossModifier):
    """Phase 2.3 — partner plays the round selfishly mid-game.

    Implementation: sets `partner_throws_trick` so the partner AI sometimes
    discards winning cards. The flag is honored by the existing AI sabotage
    paths and is restored after the blind in `_play_blind`.
    """

    id = "trahison"
    name = "La Trahison"
    description = "Partner trust is silently set to 0; partner sabotages from trick 4 onward."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_lock_trust_zero", True)
        # Re-use the existing agent_double_active flag to drive sabotage in ai.py.
        # `late_only` makes round_driver populate sabotage_tricks as 4..8 instead
        # of a random 3-trick set — matches the description "from trick 4 onward".
        state.patch("_agent_double_active", True)
        state.patch("_agent_double_late_only", True)
        return state


# ── 3.0.0: Three new boss blinds ──────────────────────────────────────────


class LeSauvage(BossModifier):
    """All Aces are worth 0 card points this round."""

    id = "le_sauvage"
    name = "Le Sauvage"
    description = "All Aces are worth 0 card points this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_aces_zero", True)
        return state


class LIconoclaste(BossModifier):
    """All Jacks are worth 0 card points this round (devastates trump suits)."""

    id = "l_iconoclaste"
    name = "L'Iconoclaste"
    description = "All Jacks are worth 0 card points — even the trump Jack."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_jacks_zero", True)
        return state


class LeMime(BossModifier):
    """Declarations (Tierce/Quarte/Carré) score zero this round.

    Note: when `separate_scoring` (La Compétition) is also active for the
    same round, declarations are already zeroed by that branch. The
    `declarations_zero` flag is then redundant but harmless — both paths
    yield 0, and `tests/belatro/test_dead_flag_fixes.py::
    test_declarations_zero_with_separate_scoring_no_double_count` pins
    that this composition stays stable.
    """

    id = "le_mime"
    name = "Le Mime"
    description = "All declarations (Tierce/Quarte/Carré) score 0 this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("_declarations_zero", True)
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
    BetrayalArc,
    LeSauvage,
    LIconoclaste,
    LeMime,
]
