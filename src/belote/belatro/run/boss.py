from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from belote.variants import RuleVariants

    from ..core.run_state import BelAtroRun
    from ..engine.modifier_patch import PatchedGameState


class BossModifier(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def apply(self, state: PatchedGameState) -> PatchedGameState:
        """Patch the GameState before the round begins."""
        ...

    def flags(self) -> RuleVariants:
        """Return the RuleVariants dataclass produced by this boss's apply().

        Useful for pre-round setup that needs to react to flags without driving
        a full round. Independent of the live GameState — uses a stub.
        """
        from belote.game import GameState, new_game
        from belote.variants import RuleVariants

        from ..engine.modifier_patch import PatchedGameState

        stub: GameState = new_game()
        proxy = PatchedGameState(stub)
        self.apply(proxy)
        patches: dict[str, object] = object.__getattribute__(proxy, "_patches")
        bm = patches.get("variants", stub.variants)
        assert isinstance(bm, RuleVariants)
        return bm

    # ── 4.11.0: expansion-only boss flags ──────────────────────────────────
    #
    # RuleVariants holds rules the *core* engine plays. A boss whose effect is
    # purely BelAtro scoring (chips / money / jokers) instead switches a flag
    # in the round's joker_state through the same `apply()` → patch path:
    # `PatchedGameState.patch("_joker_state", ...)` lands in
    # `round_driver._apply_boss`'s `replace()`, before the accumulator's
    # round start snapshots joker_state. The accumulator reads the flag —
    # never the boss id.

    @staticmethod
    def set_joker_flag(state: PatchedGameState, key: str, value: object = True) -> None:
        """Merge one scalar flag into the round's joker_state (keeps the
        deck / voucher flags already there)."""
        current = getattr(state, "_joker_state", None) or {}
        state.patch("_joker_state", {**current, key: value})

    def on_reveal(self, run: BelAtroRun) -> str | None:
        """5.0.0: a run-level effect when this boss is revealed (after the
        reveal animation, before the round). Returns a banner line, or None.
        Pure in-round bosses leave it alone."""
        return None

    def joker_flags(self) -> dict[str, object]:
        """The joker_state flags this boss's apply() switches on (may be {})."""
        from ..core.state import BelatroState
        from ..engine.modifier_patch import PatchedGameState

        proxy = PatchedGameState(BelatroState(hands=((), (), (), ())))
        self.apply(proxy)
        patches: dict[str, object] = object.__getattribute__(proxy, "_patches")
        flags = patches.get("_joker_state", {})
        assert isinstance(flags, dict)
        return dict(flags)


# ── Standard Boss Blinds (11) ──────────────────────────────────────────────


class LaGrandeMuette(BossModifier):
    id = "la_grande_muette"
    name = "La Grande Muette"
    description = "Belote/Rebelote cannot be announced. Flat 20 points removed."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("no_belote", True)
        return state


class LAnarchie(BossModifier):
    id = "l_anarchie"
    name = "L'Anarchie"
    description = "Trump changes to a random suit after every 2 tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("dynamic_trump", True)
        return state


class LeRoiMort(BossModifier):
    id = "le_roi_mort"
    name = "Le Roi Mort"
    description = "All Kings are worth 0 card points this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("kings_zero", True)
        return state


class LaMalediction(BossModifier):
    id = "la_malediction"
    name = "La Malédiction"
    description = "The team winning MORE tricks scores ZERO this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("invert_scoring", True)
        return state


class LAvocat(BossModifier):
    id = "l_avocat"
    name = "L'Avocat"
    description = "You must Coinche your own bid — target doubles, payout triples."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("auto_coinche", True)
        return state


class LeDeluge(BossModifier):
    id = "le_deluge"
    name = "Le Déluge"
    description = "All 7s and 8s become trump regardless of declared suit."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("seven_eight_trump", True)
        return state


class LaReineNoire(BossModifier):
    id = "la_reine_noire"
    name = "La Reine Noire"
    description = "Whoever captures the Queen of Spades subtracts 25 points."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("queen_spades_penalty", True)
        return state


class LeBrouillard(BossModifier):
    id = "le_brouillard"
    name = "Le Brouillard"
    description = "Score HUD is hidden until the round ends."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("hide_hud", True)
        return state


class LeBalMasque(BossModifier):
    """4.11.0: hides information that is normally public — the opponents'
    cards in the first trick stay face-down until the trick is won."""

    id = "le_bal_masque"
    name = "Le Bal Masqué"
    description = (
        "Masked ball: the opponents play their first-trick cards face-down "
        "(normally public) — revealed once the trick is won."
    )

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("masked_first_trick", True)
        return state


class LesClubsBannis(BossModifier):
    id = "les_clubs_bannis"
    name = "Les Clubs Bannis"
    description = "Clubs cannot be called as trump. Club tricks score 0."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("ban_clubs", True)
        return state


class LeZeroFinal(BossModifier):
    id = "le_zero_final"
    name = "Le Zéro Final"
    description = "The last trick is worth 0 points. Dix de Der is negated."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("no_dix_de_der", True)
        return state


class LesDixMaudits(BossModifier):
    id = "les_dix_maudits"
    name = "Les Dix Maudits"
    description = "All 10s are treated as 7s (0 point value) for this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("tens_zero", True)
        return state


# ── Partner Boss Blinds (6) ────────────────────────────────────────────────


class LaRupture(BossModifier):
    id = "la_rupture"
    name = "La Rupture"
    description = "You and partner cannot win consecutive tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("no_consecutive_team_wins", True)
        return state


class LeFantomePartenaire(BossModifier):
    id = "le_fantome_partenaire"
    name = "Le Fantôme Partenaire"
    description = "Partner's hand is invisible to you for the entire round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("hide_partner_hand", True)
        return state


class LAgentDoubleBoss(BossModifier):
    id = "l_agent_double_boss"
    name = "L'Agent Double"
    description = "Partner plays optimally for the opponents for a random 3 tricks."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("agent_double_active", True)
        return state


class LaSolitude(BossModifier):
    id = "la_solitude"
    name = "La Solitude"
    description = "Partner passes every bid. You must bid alone."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("partner_forced_pass", True)
        return state


class LeDivorce(BossModifier):
    id = "le_divorce"
    name = "Le Divorce"
    description = "Trust track is locked at 0 for this round. No Trust bonuses."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("lock_trust_zero", True)
        return state


class LaCompetition(BossModifier):
    id = "la_competition"
    name = "La Compétition"
    description = "You and partner score separately. Only higher total counts."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("separate_scoring", True)
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
        state.patch("lock_trust_zero", True)
        # Re-use the existing agent_double_active flag to drive sabotage in ai.py.
        # `late_only` makes round_driver populate sabotage_tricks as 4..8 instead
        # of a random 3-trick set — matches the description "from trick 4 onward".
        state.patch("agent_double_active", True)
        state.patch("agent_double_late_only", True)
        return state


# ── 3.0.0: Three new boss blinds ──────────────────────────────────────────


class LeSauvage(BossModifier):
    """All Aces are worth 0 card points this round."""

    id = "le_sauvage"
    name = "Le Sauvage"
    description = "All Aces are worth 0 card points this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("aces_zero", True)
        return state


class LIconoclaste(BossModifier):
    """All Jacks are worth 0 card points this round (devastates trump suits)."""

    id = "l_iconoclaste"
    name = "L'Iconoclaste"
    description = "All Jacks are worth 0 card points — even the trump Jack."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        state.patch("jacks_zero", True)
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
        state.patch("declarations_zero", True)
        return state


# ── 4.11.0: two expansion-flag bosses ─────────────────────────────────────


class LeContreAttaquant(BossModifier):
    """Opponents' Belote / Rebelote announcements rob the player."""

    id = "le_contre_attaquant"
    name = "Le Contre-Attaquant"
    description = "Each Belote or Rebelote the opponents announce steals 20 chips and $2 from you."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        from ..core.scoring import CONTRE_ATTAQUE_FLAG

        self.set_joker_flag(state, CONTRE_ATTAQUE_FLAG)
        return state


class LHuissier(BossModifier):
    """The bailiff seizes the player's leftmost joker for the round."""

    id = "l_huissier"
    name = "L'Huissier"
    description = "Your leftmost Joker is seized: it does not trigger this round."

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        from ..core.scoring import SEIZE_JOKER_FLAG

        self.set_joker_flag(state, SEIZE_JOKER_FLAG)
        return state


# ── 5.0.0: La Gangrène — the rot outlives the blind ──────────────────────

GANGRENE_FLAG = "boss_gangrene"


class LaGangrene(BossModifier):
    """Corrupts a joker for good, then keeps spreading every ante."""

    id = "la_gangrene"
    name = "La Gangrène"
    description = (
        "Rots one of your Jokers into a corrupted one — for good. The rot spreads to "
        "another Joker every ante, until your team wins a round by capot."
    )

    def apply(self, state: PatchedGameState) -> PatchedGameState:
        self.set_joker_flag(state, GANGRENE_FLAG)
        return state

    def on_reveal(self, run: BelAtroRun) -> str | None:
        run.gangrene_active = True
        rotted = rot_joker(run)
        if rotted is None:
            return "La Gangrène finds nothing to rot… yet. It will spread each ante."
        return f"La Gangrène rots {rotted}. Capot to stop it spreading!"


def rot_joker(run: BelAtroRun) -> str | None:
    """Turn one random uncorrupted joker of the player's into a random
    corrupted one (keeping its slot and edition). Returns a "Old → New" line,
    or None when there is nothing left to rot. Draws from a string-seeded RNG
    (seed, ante, cycle, count), so the run's main RNG stream is untouched."""
    import random

    from ..items.base import assign_copy_indices
    from ..items.registry import registry

    victims = [i for i, j in enumerate(run.jokers) if not j.is_corrupted]
    pool = sorted(
        j_id for j_id, cls in registry.jokers.items() if cls.is_corrupted and not cls.shop_excluded
    )
    if not victims or not pool:
        return None
    rng = random.Random(
        f"{run.seed}:gangrene:{run.ante_number}:{run.endless_ante_offset}:{run.gangrene_rotted}"
    )
    index = rng.choice(victims)
    old = run.jokers[index]
    new = registry.jokers[rng.choice(pool)]()
    new.edition = old.edition  # a Negative's slot was granted at purchase and stays
    run.jokers[index] = new
    assign_copy_indices([*run.jokers, *run.partner.jokers])
    new.on_purchase(run)  # the curse comes with it (Le Traître's sabotage...)
    run.gangrene_rotted += 1
    if run.profile is not None:
        run.profile.discover(new.id)
    if run.recorder is not None:
        run.recorder.note_acquire(new, source="la_gangrene")
    return f"{old.display_name} → {new.name}"


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
    LeContreAttaquant,
    LHuissier,
    LeBalMasque,
    # 5.0.0
    LaGangrene,
]

BOSS_BY_ID: dict[str, type[BossModifier]] = {cls.id: cls for cls in ALL_BOSS_MODIFIERS}


# ── Boss selection (4.11.0: shared by the run loop and Le Juge) ───────────


def roll_boss(run: BelAtroRun, exclude: str | None = None) -> type[BossModifier]:
    """Draw a boss from the seeded run RNG.

    A Boss Rush run with a pinned boss always gets that boss (no draw). In
    endless mode a pick from the last-2 window is rerolled (capped, so a
    degenerate pool can't loop). `exclude` (Le Juge) removes one boss from
    the pool. Without `exclude` the draw sequence is exactly the pre-4.11.0
    `_pick_boss` one, so seeded runs replay unchanged.
    """
    pinned = BOSS_BY_ID.get(run.challenge_boss_id or "")
    if pinned is not None and exclude is None:
        return pinned
    pool = ALL_BOSS_MODIFIERS
    if exclude is not None:
        pool = [cls for cls in pool if cls.id != exclude] or pool
    rng = run._get_rng()
    boss_cls: type[BossModifier] = rng.choice(pool)
    if run.endless and len(pool) > 3:
        attempts = 0
        while boss_cls.id in run._recent_boss_ids and attempts < 8:
            boss_cls = rng.choice(pool)
            attempts += 1
    return boss_cls


def peek_upcoming_boss(run: BelAtroRun) -> type[BossModifier]:
    """The next boss blind's boss, rolling (and remembering) it if needed."""
    boss_cls = BOSS_BY_ID.get(run.upcoming_boss_id or "")
    if boss_cls is None:
        boss_cls = roll_boss(run)
        run.upcoming_boss_id = boss_cls.id
    return boss_cls


def take_upcoming_boss(run: BelAtroRun) -> BossModifier:
    """Consume the upcoming boss for the boss blind about to start, and track
    it in the recent-boss window (endless repeat suppression)."""
    boss = peek_upcoming_boss(run)()
    run.upcoming_boss_id = None
    recent = run._recent_boss_ids
    recent.append(boss.id)
    if len(recent) > 2:
        del recent[: len(recent) - 2]
    return boss
