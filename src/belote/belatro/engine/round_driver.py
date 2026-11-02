from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Suit
from belote.game import (
    SANS_ATOUT_BID,
    BidValue,
    Carre,
    Phase,
    Seat,
    Sequence,
    clear_legal_cards_cache,
    legal_bids,
    new_game,
    start_round,
)
from belote.round_engine import RoundPolicy, play_round
from belote.scoring import get_declaration_points, is_capot, score_round
from belote.variants import RuleVariants

from ..core.state import BelatroState, as_belatro
from .event_bus import (
    AnyEvent,
    BeloteAnnouncedEvent,
    BidMadeEvent,
    DeclarationScoredEvent,
    EventBus,
    RoundEndEvent,
    TrickWonEvent,
)

if TYPE_CHECKING:
    from ..core.scoring import ScoreAccumulator
    from ..ghost_run import GhostRecorder
    from ..partner.partner_state import PartnerState
    from ..run.boss import BossModifier


# Defensive bound on consecutive all-pass redeals inside one drive_round call.
_MAX_REDEALS = 32


def _ew_should_coinche(state: BelatroState, rng: random.Random) -> bool:
    """Defender-side AI for the EW seats when NS is taker.

    Light, deterministic heuristic gated by the round's seeded RNG so
    behaviour is reproducible under a fixed seed (matters for ghost runs
    and replays). Baseline 20% rate; bumps to 35% if either defender holds
    2+ honour cards (Jack/Ace) — a strong defending hand suggests the NS
    contract is over-bid. Added in 3.6.0 to close audit H1 (Libra planet
    was unreachable in natural play because no path ever set
    coinche_level > 0 when NS was taker).
    """
    from belote.deck import Rank

    honors = {Rank.JACK, Rank.ACE}
    rate = 0.20
    for seat in (Seat.EAST, Seat.WEST):
        hand = state.hand_of(seat)
        if sum(1 for c in hand if c.rank in honors) >= 2:
            rate = 0.35
            break
    return rng.random() < rate


class RoundUICallbacks(ABC):
    """Interface for UI interaction during a round."""

    @abstractmethod
    def prompt_bid(self, state: BelatroState) -> BidValue: ...

    @abstractmethod
    def prompt_card(self, state: BelatroState) -> tuple[Card, BelatroState]: ...

    @abstractmethod
    def on_card_played(self, state: BelatroState, seat: Seat, card: Card) -> None: ...

    @abstractmethod
    def on_trick_end(self, state: BelatroState, winner: Seat, points: int) -> None: ...

    @abstractmethod
    def on_round_end(self, breakdown: object) -> None: ...

    def prompt_coinche(self, state: BelatroState, taker: Seat) -> bool:
        """Ask the player whether to coinche the AI's bid.

        Default no-op returns False. Override in concrete UI (e.g. BelAtro main).
        """
        return False

    def prompt_heist(self, state: BelatroState) -> bool:
        """Ask the player whether to declare a Dix de Der Heist (4.7.0).

        Fired by `drive_round` after the bidding/coinche flow and before the
        first card of trick 1, only when SOUTH is the taker. A declared heist
        bets the round on winning trick 8: success multiplies the round's
        chips × mult by `(1 + economy.interest_rate)`; failure forfeits the
        card_point chips NS earned in tricks 1-7.

        Default no-op returns False — classic Belote UI inherits this and
        never offers the heist. BelAtro overrides in `belatro/main.py`.
        """
        return False

    def prompt_special_contract(self, state: BelatroState, kind: str) -> bool:
        """5.0.0: offer to declare a Contrat Capot / Grand Chelem (`kind`) on
        a contract blind, after bidding, when the player's team holds the
        contract (see `belatro/run/contracts.py`). Default: decline."""
        return False

    def on_redeal(self, state: BelatroState) -> None:  # noqa: B027 - optional hook
        """Notify the UI that everyone passed and the cards were redealt.

        ``state`` is the fresh deal, already back in Phase.BIDDING. Default
        no-op; BelAtro main shows a short banner.
        """

    def prompt_surcoinche(self, state: BelatroState, coincheur: Seat) -> bool:
        """Ask the player whether to surcoinche (NS-taker path, 3.7.1 D3).

        Fired when the player is the taker (NS) and the EW AI lands a
        coinche — the player may surcoinche back to push `coinche_level` to
        2. Default no-op returns False; if the player declines, the existing
        AI surcoinche heuristic (30% under `surcoinche_unlocked`) still runs.
        Override in concrete UI (e.g. BelAtro main).
        """
        return False


def _diable_overcut(state: BelatroState) -> Card | None:
    """Le Diable tarot: North over-cuts whenever it legally can (one round).

    When North is following and some legal trump would take the trick, play
    the lowest such trump — even over South's winning card, which is the
    "sometimes ruinous" half of the card. Returns None (keep the AI's choice)
    when North leads, holds no winning trump, or under Sans Atout.
    """
    from belote.deck import Contract, is_trump_card, trick_rank
    from belote.game import TrickCard, legal_cards, trick_winner_seat

    trick = state.current_trick
    trump = state.trump
    if not trick or trump is None or state.contract == Contract.SANS_ATOUT:
        return None
    se = state.variants.seven_eight_trump

    def _is_trump(c: Card) -> bool:
        return is_trump_card(c, trump, se)

    winning_trumps = [
        c
        for c in legal_cards(state, Seat.NORTH)
        if _is_trump(c)
        and trick_winner_seat(trick + (TrickCard(Seat.NORTH, c),), trump, se) == Seat.NORTH
    ]
    if not winning_trumps:
        return None
    return min(winning_trumps, key=lambda c: trick_rank(c, trump, se))


@dataclass
class _RoundContext(RoundPolicy[BelatroState]):
    """BelAtro's policy over the shared round engine (`belote.round_engine`),
    plus everything one `drive_round` call threads through the round."""

    bus: EventBus
    partner: PartnerState
    ui: RoundUICallbacks
    acc: ScoreAccumulator | None
    rng: random.Random
    recorder: GhostRecorder | None
    ai_players: dict[Seat, AIPlayer] = field(default_factory=dict)
    redeals: int = 0

    def emit(self, event: AnyEvent, s: BelatroState) -> BelatroState:
        """Route an event to the accumulator, then the EventBus.

        4.6.2: process_event mutates the ledger in place (no per-event
        `replace()`); chips/mult/money are sealed once at round end. The
        ledger's joker_state IS state._joker_state (installed by
        trigger_round_start), so classic read sites see live mutations.

        4.6.4: also publish to the EventBus so external subscribers
        (UnlockTracker, ghost-run tooling) receive events. The accumulator
        runs first so its ledger mutations are visible to subscribers.
        """
        if self.acc is not None:
            self.acc.process_event(s, event)
        self.bus.emit(event)
        return s

    # ── RoundPolicy: bidding ────────────────────────────────────────────

    def choose_bid(self, state: BelatroState, seat: Seat) -> BidValue:
        return _decide_bid(self, state, seat)

    def after_bid(self, state: BelatroState, seat: Seat) -> BelatroState:
        # The BidMadeEvent's `trump` is the actual trump suit (Suit | None)
        # from state, which place_bid set correctly.
        state = self.emit(
            BidMadeEvent(seat=seat, trump=state.trump, contract=state.contract or "normal"),
            state,
        )
        if self.recorder is not None:
            self.recorder.note_bid(
                seat=seat.name.lower(),
                trump=state.trump.name.lower() if state.trump is not None else None,
                contract=state.contract or "normal",
            )
        return state

    def on_all_pass(self, state: BelatroState) -> BelatroState | None:
        """Classic Belote redeals (dealer already rotated by place_bid) and
        bidding restarts. start_round resets variants, so carry the boss/joker
        rule variants over instead of re-running setup; _joker_state (the
        ledger alias) is not reset by start_round. No RoundEndEvent fires for
        the abandoned deal, so round-end jokers never score an unplayed hand.
        The cap is purely defensive (tests that mock every seat to pass);
        past it the round ends at Phase.DEAL with 0 tricks."""
        if self.redeals >= _MAX_REDEALS:
            return None
        self.redeals += 1
        state = replace(start_round(state, self.rng), variants=state.variants)
        self.ui.on_redeal(state)
        return state

    def on_contract(self, state: BelatroState) -> BelatroState:
        state = _run_coinche(self, state)
        _offer_heist(self, state)
        _offer_special_contract(self, state)
        return state

    # ── RoundPolicy: play ───────────────────────────────────────────────

    def choose_card(self, state: BelatroState, seat: Seat) -> tuple[Card, BelatroState]:
        if seat == Seat.SOUTH:
            card, after = self.ui.prompt_card(state)
            return card, as_belatro(after)
        card = self.ai_players[seat].decide_card(state)
        if seat == Seat.NORTH and state._joker_state.get("partner_overcut_round"):
            card = _diable_overcut(state) or card
        return card, state

    def after_card(
        self, before: BelatroState, state: BelatroState, seat: Seat, card: Card
    ) -> BelatroState:
        self.ui.on_card_played(state, seat, card)
        if self.recorder is not None:
            # If the 4th card just closed the trick, completed_tricks already
            # includes it; otherwise the in-progress trick is one past.
            trick_no = len(state.completed_tricks) + (1 if state.current_trick else 0)
            self.recorder.note_play(trick=trick_no, seat=seat.name.lower(), card=str(card))
        state = _emit_belote_if_announced(self, state, seat, before.belote_tracker)
        if is_last_in_trick(state):
            state = _on_trick_complete(self, state, sum(before.current_round_points))
        return state


def drive_round(
    bus: EventBus,
    partner: PartnerState,
    ui_callbacks: RoundUICallbacks,
    acc: ScoreAccumulator | None = None,
    boss: BossModifier | None = None,
    seed: int | None = None,
    card_enhancements: dict[str, object] | None = None,
    recorder: GhostRecorder | None = None,
) -> BelatroState:
    """
    Core engine loop for a single round in BelAtro.
    Orchestrates the sequence of events (Dealing -> Bidding -> Playing -> Scoring).

    4.10.0: the round's flow is the shared `belote.round_engine.play_round`;
    `_RoundContext` is BelAtro's policy over it (partner personality,
    sabotage, heist, events, ghost recording). The seeded RNG is drawn in the
    same order as before (ghost runs and replays depend on it): deal →
    sabotage picks → bidding/redeals → coinche.
    """
    ctx = _RoundContext(
        bus=bus,
        partner=partner,
        ui=ui_callbacks,
        acc=acc,
        rng=random.Random(seed),
        recorder=recorder,
    )
    state = _setup_round(ctx, boss, card_enhancements)
    ctx.ai_players = _build_ai_players(partner, ctx.rng)
    if acc is not None:
        # Tier drives partner-joker scaling (see TrustTrack.tier).
        acc.partner_tier = partner.trust.tier

    state = play_round(state, ctx)
    if state.phase == Phase.SCORING:
        state = _run_scoring(ctx, state)

    # 4.6.2: seal the round so the returned state carries the ledger's
    # chips/mult/money. One `replace()` per round (down from ~25 pre-4.6.2).
    # `belatro/main.py::_play_blind` inspects final_state._bonus_money and
    # final_state._joker_state for round-end payout flags; sealing here
    # makes those reads see the canonical sealed values.
    if acc is not None:
        state = acc.seal_round(state)
    return state


# ── Phase: setup ────────────────────────────────────────────────────────


def _setup_round(
    ctx: _RoundContext,
    boss: BossModifier | None,
    card_enhancements: dict[str, object] | None,
) -> BelatroState:
    """Deal, merge run flags, apply the boss, pick sabotage tricks, and
    install the accumulator's ledger."""
    rng = ctx.rng
    # Target doesn't matter for a single round.
    state = start_round(as_belatro(new_game(target=1000)), rng)

    # Merge per-run deck/voucher flags into joker_state (jokers read them),
    # and switch on the core rule variants those flags stand for.
    if card_enhancements:
        state = replace(
            state,
            _joker_state={**state._joker_state, **card_enhancements},
            variants=_variants_from_flags(state.variants, card_enhancements),
        )

    # B1: Apply boss modifier flags onto the frozen BelatroState so play_card sees
    # them. Must run BEFORE acc.trigger_round_start so the accumulator's
    # snapshot of boss-derived flags (e.g. joker_state["no_dix_de_der"])
    # reflects the live boss state instead of the RuleVariants defaults.
    if boss is not None:
        state = _apply_boss(state, boss)

    # Le Traître joker (corrupted, partner_throws_trick): one random sabotage
    # trick reusing the agent_double AI path. L'Agent Double joker: two. A
    # boss that already activates agent_double takes precedence, which is why
    # these MUST run after the boss is applied. (boss.apply() draws no RNG,
    # so the seeded sequence is unchanged.)
    if state._joker_state.get("traitre_active") and not state.variants.agent_double_active:
        state = _with_sabotage(state, frozenset({rng.randint(1, 8)}))
    if (
        state._joker_state.get("agent_double_joker_active")
        and not state.variants.agent_double_active
    ):
        state = _with_sabotage(state, frozenset(rng.sample(range(1, 9), 2)))

    if ctx.acc is not None:
        state = ctx.acc.trigger_round_start(state)

    # Populate sabotage tricks for any path that flagged agent_double_active
    # without picking them: L'Agent Double boss (3 random tricks), BetrayalArc
    # (tricks 4-8 via agent_double_late_only). Reading the flag — not boss.id —
    # keeps this site reusable.
    if state.variants.agent_double_active and not state.variants.sabotage_tricks:
        if state.variants.agent_double_late_only:
            sabotage_tricks = frozenset(range(4, 9))
        else:
            sabotage_tricks = frozenset(rng.sample(range(1, 9), 3))
        # replace() keeps the same _joker_state dict object, so the ledger
        # alias survives.
        state = replace(state, variants=replace(state.variants, sabotage_tricks=sabotage_tricks))
    return state


def _apply_boss(state: BelatroState, boss: BossModifier) -> BelatroState:
    from ..engine.modifier_patch import PatchedGameState

    proxy = PatchedGameState(state)
    boss.apply(proxy)
    patches = dict(object.__getattribute__(proxy, "_patches"))
    state = replace(state, **patches)
    # Ensure boss modifiers don't use stale cached logic/values.
    clear_legal_cards_cache()
    return state


def _with_sabotage(state: BelatroState, tricks: frozenset[int]) -> BelatroState:
    """Joker-driven agent_double: the partner throws `tricks`."""
    return replace(
        state,
        variants=replace(state.variants, agent_double_active=True, sabotage_tricks=tricks),
    )


# Run-level flag (deck / voucher, see BelAtroRun.card_enhancements) → the core
# rule variant it switches on.
_FLAG_TO_VARIANT: dict[str, str] = {
    "republicain_wild": "wild_seven_eight",  # Le Républicain deck
    "no_belote_rebelote": "no_belote_rebelote",  # Le Marseillais deck
    "announce_x2": "double_declarations",  # Le Marseillais deck
    "tie_breaks_for_taker": "tie_breaks_for_taker",  # La Balance voucher
}


def _variants_from_flags(variants: RuleVariants, flags: dict[str, object]) -> RuleVariants:
    on: dict[str, Any] = {f: True for flag, f in _FLAG_TO_VARIANT.items() if flags.get(flag)}
    return replace(variants, **on) if on else variants


_DIFFICULTY_BY_NAME = {
    "easy": Difficulty.EASY,
    "medium": Difficulty.MEDIUM,
    "hard": Difficulty.HARD,
}


def _build_ai_players(partner: PartnerState, rng: random.Random) -> dict[Seat, AIPlayer]:
    # B4: the partner (North) AI uses trust-based difficulty. Every seat gets
    # the round's seeded RNG so easy-AI plays and personality jitter stay
    # reproducible under a fixed seed (ghost-run and replay tooling rely on it).
    north_diff = _DIFFICULTY_BY_NAME.get(partner.difficulty_for(Seat.NORTH), Difficulty.MEDIUM)
    return {
        Seat.EAST: AIPlayer(Seat.EAST, Difficulty.MEDIUM, rng=rng),
        Seat.NORTH: AIPlayer(Seat.NORTH, north_diff, rng=rng),
        Seat.WEST: AIPlayer(Seat.WEST, Difficulty.MEDIUM, rng=rng),
    }


# ── Phase: bidding ──────────────────────────────────────────────────────


def _decide_bid(ctx: _RoundContext, state: BelatroState, bidder: Seat) -> BidValue:
    if bidder == Seat.SOUTH:
        return ctx.ui.prompt_bid(state)
    partner = ctx.partner
    if bidder == Seat.NORTH and partner is not None and not partner.trust.ai_degraded:
        # Use the partner personality while trust is maintained.
        if state.variants.partner_forced_pass:
            return None
        if not partner.personality.should_bid(state):
            return None
        p_bid = partner.personality.bid_value(state)
        # Trust-gate Tout Atout / Sans Atout: below the threshold the partner
        # passes rather than bid a normal suit — it already chose to go big.
        is_special = p_bid == Suit.TOUT_ATOUT or p_bid == SANS_ATOUT_BID
        if is_special and not partner.trust.duo_contracts_available:
            return None
        # Only legal bids for this bidding round (place_bid itself only
        # enforces the TA/SA rule, not the up-card suit rule).
        return p_bid if p_bid in legal_bids(state) else None
    # Standard AI for EAST/WEST (and a degraded partner).
    return ctx.ai_players[bidder].decide_bid(state)


# ── Phase: coinche / surcoinche ─────────────────────────────────────────


def _run_coinche(ctx: _RoundContext, state: BelatroState) -> BelatroState:
    """Either defending team may coinche the taker's bid.

    EW taker → NS defends (player first, partner-AI fallback). NS taker → EW
    AI defends (3.6.0 audit H1: without this the Libra planet was unreachable
    in natural play). Returns the state with `coinche_level` set.
    """
    rng = ctx.rng
    level = 0
    if state.taker is not None and state.phase == Phase.PLAYING:
        surcoinche_unlocked = bool(state._joker_state.get("surcoinche_unlocked"))
        if state.taker in (Seat.EAST, Seat.WEST):
            if ctx.ui.prompt_coinche(state, state.taker) or (
                not ctx.partner.trust.ai_degraded
                and ctx.partner.personality.should_coinche(state, rng)
            ):
                level = 1
                if surcoinche_unlocked and rng.random() < 0.3:
                    level = 2
        elif _ew_should_coinche(state, rng):
            level = 1
            # When surcoinche is unlocked the player gets first refusal to
            # surcoinche back (3.7.1 D3); the AI heuristic (30%) fires if the
            # player declines. Either EW seat works as the prompt label.
            if surcoinche_unlocked and (
                ctx.ui.prompt_surcoinche(state, Seat.EAST) or rng.random() < 0.3
            ):
                level = 2

        # L'Avocat boss forces at least coinche=1 regardless of taker team.
        if state.variants.auto_coinche:
            level = max(level, 1)
        # Refresh joker_state with the resolved level via a re-emit, which
        # updates derived state without re-firing on_bid jokers.
        if level > 0:
            state = _emit_coinche(ctx, state, state.taker, level)

    # Le Coincheur deck: every round starts pre-coinched (deck mod plumbed via
    # card_enhancements → state._joker_state).
    if state.phase == Phase.PLAYING and state._joker_state.get("start_coinched") and level == 0:
        level = 1
        taker = state.taker if state.taker is not None else Seat.SOUTH
        state = _emit_coinche(ctx, state, taker, level)

    return replace(state, coinche_level=level)


def _emit_coinche(ctx: _RoundContext, state: BelatroState, seat: Seat, level: int) -> BelatroState:
    return ctx.emit(
        BidMadeEvent(
            seat=seat,
            trump=state.trump,
            contract=state.contract or "normal",
            coinche_level=level,
            re_emit=True,
        ),
        state,
    )


def _offer_heist(ctx: _RoundContext, state: BelatroState) -> None:
    """4.7.0 Dix de Der Heist declaration, after bidding/coinche settle and
    before trick 1. Only when SOUTH takes; the PLAYING guard skips the
    capped-out all-pass case (left at Phase.DEAL).

    4.8.2 (B4): single in-place write — `state._joker_state` IS the ledger's
    joker_state after trigger_round_start, so no dual-write is needed.
    """
    if state.phase == Phase.PLAYING and state.taker == Seat.SOUTH and ctx.ui.prompt_heist(state):
        state._joker_state["heist_declared"] = True


def _offer_special_contract(ctx: _RoundContext, state: BelatroState) -> None:
    """5.0.0 Contrat Capot / Grand Chelem: on a contract blind (the offer
    flag rides in from the run), once NS holds the contract the player may
    declare it. Like the heist, a single in-place joker_state write."""
    from ..run.contracts import DECLARED_KEY, OFFER_KEY

    kind = state._joker_state.get(OFFER_KEY)
    if (
        isinstance(kind, str)
        and state.phase == Phase.PLAYING
        and state.taker in (Seat.SOUTH, Seat.NORTH)
        and ctx.ui.prompt_special_contract(state, kind)
    ):
        state._joker_state[DECLARED_KEY] = kind


# ── Phase: play ─────────────────────────────────────────────────────────


def _emit_belote_if_announced(
    ctx: _RoundContext,
    state: BelatroState,
    player: Seat,
    old_tracker: tuple[bool, bool],
) -> BelatroState:
    """belote_tracker = (belote_played, rebelote_played); emit on a flip."""
    if state.belote_tracker == old_tracker:
        return state
    became_belote = state.belote_tracker[0] and not old_tracker[0]
    became_rebelote = state.belote_tracker[1] and not old_tracker[1]
    if not (became_belote or became_rebelote):
        return state
    return ctx.emit(BeloteAnnouncedEvent(seat=player, is_rebelote=became_rebelote), state)


def _on_trick_complete(ctx: _RoundContext, state: BelatroState, old_pts_total: int) -> BelatroState:
    last_trick = state.completed_tricks[-1]
    # Use the resolved winner cached by play_card (Rupture-aware). 3.8.1:
    # re-deriving via trick_winner_seat returned the RAW winner, disagreeing
    # with the team scoring authority under La Rupture.
    winner = state.last_trick_winner
    assert winner is not None, (
        "last_trick_winner unset after a complete trick — BelatroState invariant violated."
    )
    # The state diff handles all boss-aware points and Dix de Der.
    points = sum(state.current_round_points) - old_pts_total

    if len(state.completed_tricks) == 1:
        state = _emit_declarations(ctx, state)

    state = ctx.emit(
        TrickWonEvent(
            winner=winner,
            cards=tuple(tc.card for tc in last_trick),
            trick_number=len(state.completed_tricks),
            is_last=len(state.completed_tricks) == 8,
            card_points=points,
            trump=state.trump,
            leader_seat=last_trick[0].seat,
        ),
        state,
    )
    # Le Fantôme partner personality: "Every trick they win gives you +$1."
    # Personalities don't subscribe to the event bus, so the payout goes
    # through the accumulator's ledger (state._bonus_money is stale until
    # seal_round under the 4.6.2 ledger model).
    partner = ctx.partner
    if (
        partner is not None
        and getattr(partner.personality, "id", None) == "le_fantome"
        and winner == Seat.NORTH
    ):
        if ctx.acc is not None and ctx.acc._ledger is not None:
            ctx.acc._ledger.money += 1
        else:
            state = replace(state, _bonus_money=state._bonus_money + 1)
    ctx.ui.on_trick_end(state, winner, points)
    return state


def _emit_declarations(ctx: _RoundContext, state: BelatroState) -> BelatroState:
    """Declarations score after the first trick.

    Le Mime (declarations_zero) zeros declaration points in classic scoring,
    so the accumulator must see zeroed points too — otherwise chips and
    on_declaration jokers (LeMathématicien, QuinteRoyale) would credit value
    the round discards. TierceCharger keys on declaration_type only and is
    intentionally unaffected.
    """
    zeroed = state.variants.declarations_zero
    for decl in state.declarations:
        pts = 0
        if not zeroed and isinstance(decl.detail, (Sequence, Carre)):
            pts = get_declaration_points([decl.detail])
        state = ctx.emit(
            DeclarationScoredEvent(seat=decl.seat, declaration_type=decl.kind, points=pts),
            state,
        )
    return state


# ── Phase: scoring ──────────────────────────────────────────────────────


def _run_scoring(ctx: _RoundContext, state: BelatroState) -> BelatroState:
    breakdown = score_round(state)
    capot_team = is_capot(state)  # 0=NS, 1=EW, None
    state = ctx.emit(
        RoundEndEvent(
            breakdown=breakdown,
            taker_seat=state.taker,
            trump=state.trump,
            capot=capot_team is not None,
            capot_team=capot_team,
            hand_remainder=tuple(state.hand_of(Seat.SOUTH)),
            contract=state.contract or "normal",
            coinche_level=state.coinche_level,
        ),
        state,
    )
    if ctx.recorder is not None:
        ctx.recorder.note_round_end(
            {
                "taker_team": breakdown.taker_team,
                "taker_total": breakdown.taker_total,
                "defender_total": breakdown.defender_total,
                "is_capot": breakdown.is_capot,
                "is_failed": breakdown.is_failed,
            }
        )
    ctx.ui.on_round_end(breakdown)
    return state


def is_last_in_trick(state: BelatroState) -> bool:
    """Helper to check if a trick just ended."""
    return len(state.current_trick) == 0 and len(state.completed_tricks) > 0
