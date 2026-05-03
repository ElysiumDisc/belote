from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, card_points
from belote.game import (
    GameState,
    Phase,
    Seat,
    clear_announced,
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
    from ..items.base import Voucher
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


def drive_round(
    bus: EventBus,
    partner: PartnerState,
    ui_callbacks: RoundUICallbacks,
    acc: ScoreAccumulator | None = None,
    boss: BossModifier | None = None,
    target_score: int = 0,
    seed: int | None = None,
) -> GameState:
    """
    Core engine loop for a single round in BelAtro.
    Orchestrates the sequence of events (Dealing -> Bidding -> Playing -> Scoring).
    """
    rng = random.Random(seed)
    # Initialize the base game state
    state = new_game(target=1000)  # Target doesn't matter for single round
    state = start_round(state, rng)

    if acc is not None:
        state = acc.trigger_round_start(state)

    # B1: Apply boss modifier flags onto the frozen GameState so play_card sees them
    if boss is not None:
        from ..engine.modifier_patch import PatchedGameState

        _proxy = PatchedGameState(state)
        boss.apply(_proxy)
        _patches = dict(object.__getattribute__(_proxy, "_patches"))
        state = replace(state, **_patches)  # type: ignore[arg-type]

        # Ensure boss modifiers don't use stale cached logic/values
        clear_legal_cards_cache()

    # B4: Use partner trust-based difficulty for the North (partner) AI seat
    _north_diff_str = partner.difficulty_for(Seat.NORTH)
    _north_diff = Difficulty.EASY if _north_diff_str == "easy" else Difficulty.MEDIUM
    ai_players = {
        Seat.EAST: AIPlayer(Seat.EAST, Difficulty.MEDIUM),
        Seat.NORTH: AIPlayer(Seat.NORTH, _north_diff),
        Seat.WEST: AIPlayer(Seat.WEST, Difficulty.MEDIUM),
    }

    if acc is not None:
        acc.partner_jokers_double = partner.trust.partner_jokers_double

    def _emit(event: object, s: GameState) -> GameState:
        if acc is not None:
            return acc.update_state(s, event)
        return s

    # Phase: BIDDING
    while state.phase == Phase.BIDDING:
        bidder = state.turn
        bid: Suit | None = None

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
                # Ensure the bid is legal for the current round
                forbidden = state.up_card.suit if state.up_card else None
                if p_bid != forbidden:
                    bid = p_bid
        else:
            # Standard AI for EAST/WEST
            bid = ai_players[bidder].decide_bid(state)

        state = process_bid(state, bid)
        state = _emit(
            BidMadeEvent(
                seat=bidder,
                trump=bid,
                contract=state.contract or "normal",
            ),
            state
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

        state = play_card(state, card)
        ui_callbacks.on_card_played(state, player, card)

        if is_last_in_trick(state):
            last_trick = state.completed_tricks[-1]

            winner = trick_winner_seat(
                last_trick, state.trump, state.boss_modifiers.seven_eight_trump
            )
            # Use state diff to get points; perfectly handles all boss-aware points and Dix de Der
            points = sum(state.current_round_points) - old_pts_total

            # Emit declarations first if it's the first trick
            if len(state.completed_tricks) == 1:
                for decl in state.declarations:
                    pts = 0
                    if decl.detail and decl.kind in ("sequence", "carre"):
                        # Correctly calculate declaration points using scoring utility
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
            state = _emit(
                TrickWonEvent(
                    winner=winner,
                    cards=cards,
                    trick_number=len(state.completed_tricks),
                    is_last=is_last,
                    card_points=points,
                    trump=state.trump,
                ),
                state
            )
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
            ),
            state
        )
        ui_callbacks.on_round_end(breakdown)
    
    return state


def is_last_in_trick(state: GameState) -> bool:
    """Helper to check if a trick just ended."""
    return len(state.current_trick) == 0 and len(state.completed_tricks) > 0
