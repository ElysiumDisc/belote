from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Suit
from belote.game import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
    Phase,
    Seat,
    clear_legal_cards_cache,
    new_game,
    play_card,
    process_bid,
    start_round,
    trick_winner_seat,
)
from belote.scoring import get_declaration_points, is_capot, score_round

from .event_bus import (
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


class RoundUICallbacks(ABC):
    """Interface for UI interaction during a round."""

    @abstractmethod
    def prompt_bid(self, state: GameState) -> Suit | None: ...

    @abstractmethod
    def prompt_card(self, state: GameState) -> tuple[Card, GameState]: ...

    @abstractmethod
    def on_card_played(self, state: GameState, seat: Seat, card: Card) -> None: ...

    @abstractmethod
    def on_trick_end(self, state: GameState, winner: Seat, points: int) -> None: ...

    @abstractmethod
    def on_round_end(self, breakdown: object) -> None: ...

    def prompt_coinche(self, state: GameState, taker: Seat) -> bool:
        """Ask the player whether to coinche the AI's bid.

        Default no-op returns False. Override in concrete UI (e.g. BelAtro main).
        """
        return False


def drive_round(
    bus: EventBus,
    partner: PartnerState,
    ui_callbacks: RoundUICallbacks,
    acc: ScoreAccumulator | None = None,
    boss: BossModifier | None = None,
    target_score: int = 0,
    seed: int | None = None,
    card_enhancements: dict[str, object] | None = None,
    recorder: GhostRecorder | None = None,
) -> GameState:
    """
    Core engine loop for a single round in BelAtro.
    Orchestrates the sequence of events (Dealing -> Bidding -> Playing -> Scoring).
    """
    rng = random.Random(seed)
    # Initialize the base game state
    state = new_game(target=1000)  # Target doesn't matter for single round
    state = start_round(state, rng)

    # Merge per-run deck/voucher flags so scoring/legal_cards can read them.
    if card_enhancements:
        new_jstate = {**state._joker_state, **card_enhancements}
        state = replace(state, _joker_state=new_jstate)

    # Le Traître joker (corrupted, partner_throws_trick): pick one random trick
    # for partner sabotage and reuse the existing agent_double AI path. Skip if
    # a boss already activates agent_double — its 3-trick set takes precedence.
    if state._joker_state.get("traitre_active") and not state.boss_modifiers.agent_double_active:
        sabotage = frozenset({rng.randint(1, 8)})
        new_bm = replace(state.boss_modifiers, agent_double_active=True)
        new_jstate2 = {**state._joker_state, "agent_double_tricks": sabotage}
        state = replace(state, boss_modifiers=new_bm, _joker_state=new_jstate2)

    if acc is not None:
        state = acc.trigger_round_start(state)

    # B1: Apply boss modifier flags onto the frozen GameState so play_card sees them
    if boss is not None:
        from ..engine.modifier_patch import PatchedGameState

        _proxy = PatchedGameState(state)
        boss.apply(_proxy)
        _patches = dict(object.__getattribute__(_proxy, "_patches"))
        state = replace(state, **_patches)

        # Ensure boss modifiers don't use stale cached logic/values
        clear_legal_cards_cache()

    # Populate sabotage_tricks for any path that flagged agent_double_active.
    # Sources: L'Agent Double boss (3 random tricks), BetrayalArc (tricks 4-8 via
    # agent_double_late_only flag), traitre joker (already populated above).
    # Reading the flag — not boss.id — keeps this site reusable.
    if state.boss_modifiers.agent_double_active and not state._joker_state.get(
        "agent_double_tricks"
    ):
        if state.boss_modifiers.agent_double_late_only:
            sabotage_tricks = frozenset(range(4, 9))
        else:
            sabotage_tricks = frozenset(rng.sample(range(1, 9), 3))
        new_jstate = {**state._joker_state, "agent_double_tricks": sabotage_tricks}
        state = replace(state, _joker_state=new_jstate)

    # B4: Use partner trust-based difficulty for the North (partner) AI seat
    _north_diff_str = partner.difficulty_for(Seat.NORTH)
    _north_diff = {
        "easy": Difficulty.EASY,
        "medium": Difficulty.MEDIUM,
        "hard": Difficulty.HARD,
    }.get(_north_diff_str, Difficulty.MEDIUM)
    ai_players = {
        Seat.EAST: AIPlayer(Seat.EAST, Difficulty.MEDIUM),
        Seat.NORTH: AIPlayer(Seat.NORTH, _north_diff),
        Seat.WEST: AIPlayer(Seat.WEST, Difficulty.MEDIUM),
    }

    if acc is not None:
        acc.partner_jokers_double = partner.trust.partner_jokers_double
        acc.partner_tier = partner.trust.tier

    def _emit(event: object, s: GameState) -> GameState:
        if acc is not None:
            return acc.update_state(s, event)
        return s

    # Phase: BIDDING
    while state.phase == Phase.BIDDING:
        bidder = state.turn
        bid: BidValue = None

        if bidder == Seat.SOUTH:
            bid = ui_callbacks.prompt_bid(state)
        elif (
            bidder == Seat.NORTH
            and partner is not None
            and not partner.trust.ai_degraded
        ):
            # Use personality for the partner if trust is maintained
            if state.boss_modifiers.partner_forced_pass:
                bid = None
            elif partner.personality.should_bid(state):
                p_bid = partner.personality.bid_value(state)
                # Trust-gate Tout Atout / Sans Atout: partner only bids these
                # special contracts once the trust track unlocks them. Below
                # the threshold, fall through to "pass" rather than bid a
                # normal suit — the personality already chose to go big.
                is_special = p_bid == Suit.TOUT_ATOUT or p_bid == SANS_ATOUT_BID
                if is_special and not partner.trust.duo_contracts_available:
                    p_bid = None
                # Ensure the bid is legal for the current round (round 1 = up
                # card suit only). TA/SA are also rejected in round 1 by
                # place_bid, but we filter early to keep the bid legal here.
                forbidden = state.up_card.suit if state.up_card else None
                if p_bid != forbidden and not (
                    is_special and state.bidding_round == 1
                ):
                    bid = p_bid
        else:
            # Standard AI for EAST/WEST
            bid = ai_players[bidder].decide_bid(state)

        state = process_bid(state, bid)
        # `bid` was a BidValue; the BidMadeEvent's `trump` field is the actual
        # trump suit (Suit | None) from state, which place_bid set correctly.
        state = _emit(
            BidMadeEvent(
                seat=bidder,
                trump=state.trump,
                contract=state.contract or "normal",
            ),
            state
        )
        if recorder is not None:
            recorder.note_bid(
                seat=bidder.name.lower(),
                trump=state.trump.name.lower() if state.trump is not None else None,
                contract=state.contract or "normal",
            )

    # ── Coinche / surcoinche player flow ─────────────────────────────────
    # If a taker emerged on the opposing (EW) team, give the player a chance
    # to coinche; if they coinche, give the AI taker a chance to surcoinche.
    coinche_level = 0
    if (
        state.taker is not None
        and state.taker in (Seat.EAST, Seat.WEST)
        and state.phase == Phase.PLAYING
    ):
        if ui_callbacks.prompt_coinche(state, state.taker):
            coinche_level = 1
            # AI surcoinche: simple heuristic — 30% under the seeded RNG.
            # Surcoinche is gated by La Surcoinche voucher (when piped in).
            surcoinche_unlocked = bool(state._joker_state.get("surcoinche_unlocked"))
            if surcoinche_unlocked and rng.random() < 0.3:
                coinche_level = 2
            # L'Avocat boss forces at least coinche=1 (existing auto_coinche flag).
        if state.boss_modifiers.auto_coinche:
            coinche_level = max(coinche_level, 1)
        # Re-emit the final BidMadeEvent so jokers/HUD see the coinche level.
        if coinche_level > 0:
            state = _emit(
                BidMadeEvent(
                    seat=state.taker,
                    trump=state.trump,
                    contract=state.contract or "normal",
                    coinche_level=coinche_level,
                ),
                state,
            )
    elif state.boss_modifiers.auto_coinche and state.phase == Phase.PLAYING:
        # Boss forces coinche even if taker is on NS team.
        coinche_level = 1
        # Re-emit BidMadeEvent so jokers/HUD subscribed to on_bid see the
        # coinche level. The EW-taker branch above does this; this NS branch
        # used to skip it, silently dropping the event for on_bid subscribers.
        if state.taker is not None:
            state = _emit(
                BidMadeEvent(
                    seat=state.taker,
                    trump=state.trump,
                    contract=state.contract or "normal",
                    coinche_level=coinche_level,
                ),
                state,
            )

    # Le Coincheur deck: every round starts pre-coinched (deck mod plumbed via
    # card_enhancements → state._joker_state).
    if (
        state.phase == Phase.PLAYING
        and state._joker_state.get("start_coinched")
        and coinche_level == 0
    ):
        coinche_level = 1
        state = _emit(
            BidMadeEvent(
                seat=state.taker if state.taker is not None else Seat.SOUTH,
                trump=state.trump,
                contract=state.contract or "normal",
                coinche_level=coinche_level,
            ),
            state,
        )

    # If round ended early (everyone passed), emit RoundEndEvent
    if state.phase == Phase.DEAL and len(state.bids) == 0:
        # Everyone passed; state moved back to DEAL by process_bid
        # We need a breakdown to emit.
        breakdown = score_round(state)
        state = _emit(
            RoundEndEvent(
                breakdown=breakdown,
                taker_seat=None,
                trump=None,
                capot=False,
                hand_remainder=tuple(state.hand_of(Seat.SOUTH)),
                contract=state.contract or "normal",
                coinche_level=coinche_level,
            ),
            state
        )

    # Phase: PLAYING
    while state.phase == Phase.PLAYING:
        player = state.turn
        card: Card | None = None

        if player == Seat.SOUTH:
            card, state = ui_callbacks.prompt_card(state)
        else:
            # AI Play
            card = ai_players[player].decide_card(state)

        # Before playing, track points to emit TrickWonEvent with diff
        old_pts_total = sum(state.current_round_points)
        old_belote_tracker = state.belote_tracker

        state = play_card(state, card)
        ui_callbacks.on_card_played(state, player, card)
        if recorder is not None:
            # If the 4th card just closed the trick, completed_tricks already
            # includes it; otherwise we're mid-trick and the in-progress trick
            # number is one past the completed count.
            trick_no = (
                len(state.completed_tricks)
                if not state.current_trick
                else len(state.completed_tricks) + 1
            )
            recorder.note_play(trick=trick_no, seat=player.name.lower(), card=str(card))

        # If this play flipped the belote tracker, emit the announce event.
        # belote_tracker = (belote_played, rebelote_played); compare old vs new.
        if state.belote_tracker != old_belote_tracker:
            became_belote = state.belote_tracker[0] and not old_belote_tracker[0]
            became_rebelote = state.belote_tracker[1] and not old_belote_tracker[1]
            if became_belote or became_rebelote:
                state = _emit(
                    BeloteAnnouncedEvent(seat=player, is_rebelote=became_rebelote),
                    state,
                )

        if is_last_in_trick(state):
            last_trick = state.completed_tricks[-1]

            winner = trick_winner_seat(
                last_trick,
                state.trump,
                state.boss_modifiers.seven_eight_trump,
                state.contract == "sans_atout",
            )
            # Use state diff to get points; perfectly handles all boss-aware points and Dix de Der
            points = sum(state.current_round_points) - old_pts_total

            # Emit declarations first if it's the first trick
            if len(state.completed_tricks) == 1:
                for decl in state.declarations:
                    pts = 0
                    if decl.detail and decl.kind in ("sequence", "carre"):
                        pts = get_declaration_points([decl.detail])
                    state = _emit(
                        DeclarationScoredEvent(
                            seat=decl.seat,
                            declaration_type=decl.kind,
                            points=pts,
                        ),
                        state
                    )

            is_last = len(state.completed_tricks) == 8
            cards = tuple(tc.card for tc in last_trick)
            leader_seat = last_trick[0].seat
            state = _emit(
                TrickWonEvent(
                    winner=winner,
                    cards=cards,
                    trick_number=len(state.completed_tricks),
                    is_last=is_last,
                    card_points=points,
                    trump=state.trump,
                    leader_seat=leader_seat,
                ),
                state
            )
            # Le Fantôme partner personality: "Every trick they win gives you
            # +$1." Personalities don't subscribe to the event bus the way
            # jokers do, so payout is wired through state._bonus_money here.
            if (
                partner is not None
                and getattr(partner.personality, "id", None) == "le_fantome"
                and winner == Seat.NORTH
            ):
                state = replace(state, _bonus_money=state._bonus_money + 1)
            ui_callbacks.on_trick_end(state, winner, points)

    # Round End / Scoring
    if state.phase == Phase.SCORING:
        breakdown = score_round(state)
        hand_remainder = tuple(state.hand_of(Seat.SOUTH))
        state = _emit(
            RoundEndEvent(
                breakdown=breakdown,
                taker_seat=state.taker,
                trump=state.trump,
                capot=is_capot(state) is not None,
                hand_remainder=hand_remainder,
                contract=state.contract or "normal",
                coinche_level=coinche_level,
            ),
            state
        )
        if recorder is not None:
            recorder.note_round_end({
                "taker_team": breakdown.taker_team,
                "taker_total": breakdown.taker_total,
                "defender_total": breakdown.defender_total,
                "is_capot": breakdown.is_capot,
                "is_failed": breakdown.is_failed,
            })
        ui_callbacks.on_round_end(breakdown)

    return state


def is_last_in_trick(state: GameState) -> bool:
    """Helper to check if a trick just ended."""
    return len(state.current_trick) == 0 and len(state.completed_tricks) > 0
