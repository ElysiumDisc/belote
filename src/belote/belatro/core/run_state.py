from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..items.base import Joker, Voucher
    from ..progression.save import Profile
    from ..run.ante import Ante
    from ..ui.history import BelAtroHistoryEntry

from ..partner.partner_state import PartnerState
from .economy import Economy

MAX_JOKER_SLOTS = 5
DEFAULT_CONSUMABLE_SLOTS = 2


@dataclass
class BelAtroRun:
    """Top-level mutable state for one complete Belatro run."""

    # ── Progression ────────────────────────────────────────
    ante_number: int = 1  # 1–8
    blind_index: int = 0  # 0=Small, 1=Big, 2=Boss
    run_over: bool = False
    run_won: bool = False
    profile: Profile | None = None

    # ── Collectibles ───────────────────────────────────────
    # These lists are intentionally mutable: jokers append on purchase, vouchers
    # apply their effects in-place, and `consume()` removes items via
    # `consumables.remove(item)`. If a future feature needs to snapshot a run
    # for replay / ghost-run reconstruction, deep-copy these lists at the
    # snapshot boundary — they alias live state otherwise.
    jokers: list[Joker] = field(default_factory=list)
    vouchers: list[Voucher] = field(default_factory=list)
    consumables: list[Any] = field(default_factory=list)  # Tarot/Planet instances
    joker_slots: int = MAX_JOKER_SLOTS
    consumable_slots: int = DEFAULT_CONSUMABLE_SLOTS

    # ── Permanent run bonuses (from Tarot cards) ───────────
    permanent_chips: int = 0
    permanent_mult: float = 1.0

    # ── Voucher flags ───────────────────────────────────────
    guarantee_tarot_in_shop: bool = False
    show_partner_bid_tendency: bool = False
    tie_breaks_for_taker: bool = False
    partner_throws_trick: bool = False  # Le Traître joker (1 random trick/round)
    agent_double_joker: bool = False  # L'Agent Double joker (2 random tricks/round)
    capot_insurance: bool = False  # one-shot: halve a chute loss

    # ── Phase 1+ feature flags ──────────────────────────────
    tierce_charges: int = 0
    legendary_unlocked: set[str] = field(default_factory=set)
    endless: bool = False
    endless_ante_offset: int = 0
    ante_theme: str | None = None
    partner_mood: str = "neutral"

    # ── Economy ────────────────────────────────────────────
    economy: Economy = field(default_factory=Economy)

    # ── Partner ────────────────────────────────────────────
    partner: PartnerState = field(default_factory=PartnerState)

    # ── Deck ───────────────────────────────────────────────
    deck_id: str = "classique"
    card_enhancements: dict[str, Any] = field(default_factory=dict)  # card_id → Enhancement
    show_north_hand: bool = False  # set True by LeCarnet voucher
    # 3.6.0 audit R4: typed via `ContractReward` (TypedDict) at the consuming
    # site (`belatro.core.scoring.ScoreAccumulator`). Stored here as the wider
    # `dict[str, dict]` to avoid an import cycle through items/planets; the
    # consumer's TypedDict-annotated reads still get IDE/type-checker support.
    contract_levels: dict[str, dict[str, Any]] = field(default_factory=dict)
    gold_seal_aces: bool = False  # L'Aristocrate: Aces won → +$1 each
    corrupted_pool_visible: bool = False  # L'Anarchiste: corrupted shop pool revealed
    surcoinche_unlocked: bool = False  # La Surcoinche voucher: enables AI surcoinche
    partner_joker_offers: bool = False  # Le Téléphone voucher: shop may stock a partner joker

    # ── Last consumable used (read by LeFou tarot) ─────────
    last_consumable_id: str | None = None

    # ── Last tarot status message ──────────────────────────
    # Set by tarots that need to surface a non-fatal failure (e.g. LeJugement
    # rolling a joker when joker_slots are full). The UI may read and display
    # this; tests assert it. Cleared whenever a new tarot is used.
    last_tarot_message: str | None = None

    # ── Per-blind history (powers the [H] overlay) ─────────
    # Appended by `BelAtroGame._play_blind` after each Belote round. The
    # classic `state.score_history` is never written under BelAtro (see
    # `belatro/ui/history.py` header for the full rationale).
    history: list[BelAtroHistoryEntry] = field(default_factory=list)

    # ── Determinism ────────────────────────────────────────
    seed: int | None = None
    # ISO date when this is a Daily Challenge run (see belatro/daily.py):
    # starter shop pool, no endless offer.
    daily: str | None = None
    _rng: Any = None

    # ── 4.11.0: Boss Rush / Challenge Seed ─────────────────
    # `challenge` marks a run started from the Boss Rush screen: it plays the
    # normal run loop but doesn't count toward run-level milestones (runs
    # won, ante unlocks, bosses defeated) — starting at Ante 8 would farm them.
    challenge: bool = False
    boss_rush: bool = False  # every blind is a boss blind
    challenge_boss_id: str | None = None  # pin every boss blind to this boss

    # ── 4.11.0: upcoming boss (Le Juge tarot) ──────────────
    # The next boss blind's boss, rolled lazily: `_pick_boss` rolls it at the
    # boss blind exactly as before (same RNG draw), unless Le Juge already
    # rolled — and rerolled — it from the shop. `boss_reroll_ante` remembers
    # the ante (+ endless cycle) Le Juge was last used in: once per ante.
    upcoming_boss_id: str | None = None
    boss_reroll_ante: tuple[int, int] | None = None

    # ── 4.11.0: ghost-run recorder ─────────────────────────
    # Set by BelAtroGame when ghost recording is on; the shop and `consume()`
    # report purchases / sells / rerolls / uses through it. Never serialised.
    recorder: Any = field(default=None, repr=False, compare=False)

    # ── Idempotency guard for voucher.apply() ──────────────
    # Several vouchers (LaTelescope, LaDoubleDonne, LesCartesDorees, LeCouteau)
    # use `+=` against run-level counters in their `apply()`. The guard now
    # lives on `Voucher.apply()` (3.9.3 R5) so any caller — shop, replay, a
    # future save/load round-trip — gets the same protection automatically.
    _applied_voucher_ids: set[str] = field(default_factory=set)

    # ── Idempotency guard for Joker.on_purchase() ──────────
    # Corrupted jokers with non-idempotent on_purchase actions (LeDemon's
    # trust subtraction) record their id here on first apply. Re-application
    # paths (a future save/load round-trip, replay tooling) consult this set
    # and short-circuit so a once-paid cost never compounds. Joker on_purchase
    # actions that are already idempotent (boolean flags like
    # LeTraitre.partner_throws_trick, LAgentDouble.agent_double_joker) don't
    # need to consult this set, but adding their id is harmless. 4.7.3.
    _applied_purchase_ids: set[str] = field(default_factory=set)

    # ── 5.0.0: L'Atelier — per-card enhancements and seals ─
    # card_key (e.g. "ACE_HEARTS") → CardMod. See core/card_mods.py.
    card_mods: dict[str, Any] = field(default_factory=dict)

    # ── 5.0.0: Médailles (run/medals.py) ───────────────────
    # Earned medals waiting for the next shop, which consumes them all.
    medals: list[str] = field(default_factory=list)
    medals_earned: int = 0
    blinds_skipped: int = 0
    # (ante, endless cycle) that already paid a feat medal — one per ante.
    feat_medal_ante: tuple[int, int] | None = None

    # ── 5.0.0: Capot / Grand Chelem contracts (run/contracts.py) ──
    capot_contracts_won: int = 0

    # ── 5.0.0: partner story beats (partner/story.py) ──────
    story_seen: set[str] = field(default_factory=set)
    # One-shot buff granted by the last beat, spent by the next round:
    # {"chips": int, "mult": float, "times_mult": float}.
    story_buff: dict[str, float] = field(default_factory=dict)
    # Facts the beats key on that aren't in the history.
    sabotage_seen: bool = False

    # ── 5.0.0: L'Usurier — the shop's loan (run/usurier.py) ─
    loan_debt: int = 0
    loans_taken: int = 0

    # ── 5.0.0: La Gangrène boss — the rot spreads each ante ─
    gangrene_active: bool = False
    gangrene_rotted: int = 0

    # ── Recent-boss tracker (3.9.3 Phase 5) ────────────────
    # Used by the BelAtro main loop to suppress immediate boss repeats in
    # endless mode. The deque holds at most 2 recent boss ids; the selector
    # rerolls if its pick is in this window. Empty by default — bounded so
    # the run-state JSON snapshot stays small.
    _recent_boss_ids: list[str] = field(default_factory=list)

    def consume(self, item: Any, context: object = None) -> bool:
        """Centralised consumable activation.

        Removes the item from `consumables` if present, dispatches to the right
        hook based on item type (Tarot vs Planet), then advances
        `last_consumable_id` so Le Fou can copy the prior consumable later.

        Apply order matters: `item.use()` must run BEFORE updating
        `last_consumable_id`, because Le Fou's `use()` reads that field to
        find what to copy — if we advanced it to `le_fou` first, Le Fou would
        see itself and fall through to the fallback path. Le Fou itself is
        treated as transparent: the bookmark stays pointed at the source it
        copied, so a second Le Fou keeps copying the same source rather than
        copying itself.

        4.11.0: returns False — leaving the card in the tray — when a tarot's
        `refusal()` says it can't be used right now (the reason lands in
        `last_tarot_message`). Uses and any joker they grant (Le Jugement)
        are reported to the ghost recorder.
        """
        import contextlib

        from ..items.base import Planet, Tarot

        self.last_tarot_message = None
        if isinstance(item, Tarot):
            reason = item.refusal(self)
            if reason is not None:
                self.last_tarot_message = reason
                return False
        jokers_before = list(self.jokers)
        with contextlib.suppress(ValueError):
            self.consumables.remove(item)
        if isinstance(item, Tarot):
            item.use(self, context)
        elif isinstance(item, Planet):
            item.use(self)
        # Le Fou is transparent — leave the bookmark at the source it copied.
        # Every other consumable advances the bookmark to its own id.
        if getattr(item, "id", None) != "le_fou":
            self.last_consumable_id = getattr(item, "id", None)
        if self.recorder is not None:
            self.recorder.note_use(item)
            for joker in self.jokers:
                if all(joker is not j for j in jokers_before):
                    self.recorder.note_acquire(joker, source=getattr(item, "id", "?"))
        return True

    def add_joker(self, joker: Joker) -> None:
        """Put `joker` in the player's slots (the caller checked capacity),
        give it its own copy index, then fire its purchase hook (5.0.0: the
        one path the shop, tarots and Le Serment all take)."""
        from ..items.base import assign_copy_indices

        self.jokers.append(joker)
        assign_copy_indices([*self.jokers, *self.partner.jokers])
        joker.on_purchase(self)

    def _get_rng(self) -> Any:
        """Per-run random.Random instance, seeded from `seed` when given."""
        if self._rng is None:
            import random as _random

            self._rng = _random.Random(self.seed) if self.seed is not None else _random.Random()
        return self._rng

    def __post_init__(self) -> None:
        from ..items.registry import register_all_items, registry
        from ..run.decks import STARTING_DECKS

        # Pick a concrete seed when none was given so every run is replayable
        # from `seed` (ghost runs record it). Must happen before the first
        # `_get_rng()` call below. Drawn from the module RNG, so unseeded runs
        # stay as random as before.
        if self.seed is None and self._rng is None:
            import random as _random

            self.seed = _random.getrandbits(32)

        if not registry.planets:
            register_all_items()

        deck = next((d for d in STARTING_DECKS if d.id == self.deck_id), None)
        if deck is not None:
            self._apply_starting_deck(deck, registry)

    # Deck modifications copied verbatim into `card_enhancements` (read by the
    # round driver / scoring / main). Two groups so the dict keeps its
    # historical insertion order around `republicain_wild`.
    #   start_coinched / announce_x2 / no_belote_rebelote: Phase 2.4 decks.
    #   boss_every_2: Le Joueur also rolls a boss on even antes' Big Blind.
    #   ghost_lead: L'Infiltré pays +2 mult / +$1 for a void-trump trick win.
    #   buy_contract / annonce_cash_x2: L'Architecte's $10 contract purchase
    #   and +$2 per NS trick holding a declared-annonce card.
    _DECK_FLAGS_EARLY: ClassVar[tuple[str, ...]] = (
        "start_coinched",
        "announce_x2",
        "no_belote_rebelote",
        "boss_every_2",
    )
    _DECK_FLAGS_LATE: ClassVar[tuple[str, ...]] = ("ghost_lead", "buy_contract", "annonce_cash_x2")

    def boss_reroll_key(self) -> tuple[int, int]:
        """The (ante, endless cycle) Le Juge's once-per-ante limit keys on."""
        return (self.ante_number, self.endless_ante_offset)

    def _apply_starting_deck(self, deck: Any, registry: Any) -> None:
        """Starting money, jokers, a free planet, and the deck's rule flags."""
        from ..items.base import assign_copy_indices

        mods = deck.deck_modifications
        self.economy.money = deck.initial_money
        for joker_id in deck.initial_jokers:
            joker_cls = registry.get_joker(joker_id)
            if joker_cls:
                self.jokers.append(joker_cls())
                assign_copy_indices(self.jokers)
                if self.profile:
                    self.profile.discover(joker_id)

        if mods.get("free_planet"):
            self._grant_free_planet(registry)

        if mods.get("start_chips_bonus"):
            self.permanent_chips += int(mods["start_chips_bonus"])
        for flag in self._DECK_FLAGS_EARLY:
            if mods.get(flag):
                self.card_enhancements[flag] = True
        if mods.get("gold_seal_aces"):
            self._seal_gold_aces()
        if mods.get("corrupted_pool_visible"):
            self.corrupted_pool_visible = True
        if self.deck_id == "republicain":
            # 7s/8s are wild; legal_cards reads this flag from _joker_state.
            self.card_enhancements["republicain_wild"] = True
        for flag in self._DECK_FLAGS_LATE:
            if mods.get(flag):
                self.card_enhancements[flag] = True
        # 4.11.0 Le Complice: partner starts trusted, with a partner joker
        # in its own slot (drawn from the seeded run RNG).
        if mods.get("partner_trust"):
            self.partner.trust.value = int(mods["partner_trust"])
        if mods.get("partner_joker"):
            self._grant_partner_joker(registry)

    def _seal_gold_aces(self) -> None:
        """L'Aristocrate: the four Aces carry a Sceau d'Or (5.0.0: in the
        per-card layer, `card_mods`)."""
        from belote.deck import Card, Rank, Suit

        from .card_mods import apply_mod

        self.gold_seal_aces = True
        for suit in (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS):
            apply_mod(self.card_mods, Card(suit, Rank.ACE), "or")

    def _grant_partner_joker(self, registry: Any) -> None:
        """Equip one random partner joker on the partner's own slots."""
        pool = sorted(j_id for j_id, cls in registry.jokers.items() if cls.is_partner_joker)
        if not pool:
            return
        j_id = self._get_rng().choice(pool)
        self.partner.equip_joker(registry.jokers[j_id](), self)
        if self.profile:
            self.profile.discover(j_id)

    def _grant_free_planet(self, registry: Any) -> None:
        """One random contract level-up at run start (seeded run RNG)."""
        planet_ids = list(registry.planets.keys())
        if not planet_ids:
            return
        p_id = self._get_rng().choice(planet_ids)
        planet_cls = registry.get_planet(p_id)
        if planet_cls:
            if self.profile:
                self.profile.discover(p_id)
            planet_instance = planet_cls()
            self.contract_levels[planet_instance.contract_id] = planet_instance.level_up_reward()

    # ── Current blind target ───────────────────────────────
    @property
    def current_blind(self) -> Ante:
        from ..run.ante import ANTE_TABLE, endless_ante

        if self.endless and self.endless_ante_offset > 0:
            return endless_ante(self.ante_number, self.blind_index, self.endless_ante_offset)
        return ANTE_TABLE[self.ante_number - 1][self.blind_index]

    @property
    def target_score(self) -> int:
        base = self.current_blind.target
        theme = self.get_ante_theme()
        if theme is None:
            return base
        # Soft target adjustments (e.g. Café reduces boss target by 5%).
        # Round to int after the float multiply so downstream scoring
        # comparisons stay integral.
        mult: float = theme.target_multiplier(self.blind_index)
        return max(1, round(base * mult))

    def get_ante_theme(self) -> Any:
        """Resolve `ante_theme` (id) back to an AnteTheme instance, or None."""
        if not self.ante_theme:
            return None
        from ..run.ante_themes import THEME_BY_ID

        cls = THEME_BY_ID.get(self.ante_theme)
        return cls() if cls is not None else None

    def advance_blind(self) -> None:
        if self.blind_index < 2:
            self.blind_index += 1
            return
        # End of an ante.
        if self.ante_number < 8:
            self.ante_number += 1
            self.blind_index = 0
            return
        # End of ante 8.
        if self.endless:
            # Stay at ante 8, increment endless offset, restart blind cycle.
            self.endless_ante_offset += 1
            self.blind_index = 0
            return
        # Standard run completion. Set both flags so the terminal-state
        # invariant (run_over ⇔ run is over, run_won ⇔ run is over AND we won)
        # is consistent; main.py's loop break still handles the exit but
        # downstream callers can now rely on run_over alone.
        self.run_won = True
        self.run_over = True

    def enter_endless(self) -> None:
        """Toggle endless mode after beating ante 8.

        Pre-3.4.0 the loop continued at (ante=8, blind=2, offset=0), which made
        the *first* endless round replay the Ante 8 Boss Blind at the same
        target before the ×2.2 scaling kicked in on the next cycle. We now
        advance into a fresh endless cycle here so the prompt's "Ante 9+ scales
        ×2.2" is honoured immediately.
        """
        self.endless = True
        self.run_won = False  # endless overrides run-won state
        self.run_over = False  # ...and re-opens the run so the main loop continues
        # Skip the redundant Ante 8 Boss replay: bump offset and restart the
        # blind cycle. max(...) preserves any externally-set offset (tests).
        self.endless_ante_offset = max(self.endless_ante_offset, 1)
        self.blind_index = 0
