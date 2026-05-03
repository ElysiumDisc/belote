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
    new_game,
    play_card,
    process_bid,
    start_round,
)
from belote.scoring import is_capot, score_round

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
    def prompt_bid(self, state: GameState) -> object: ...
    @abstractmethod
    def prompt_card(self, state: GameState) -> tuple[Card, GameState]: ...
    @abstractmethod
    def on_card_played(self, state: GameState, seat: Seat, card: Card) -> None: ...
    @abstractmethod
    def on_trick_end(self, state: GameState, winner: Seat, points: int) -> None: ...
    @abstractmethod
    def on_round_end(self, breakdown: object) -> None: ...


def drive_round(
    *,
    bus: EventBus,
    partner: PartnerState,
    boss: BossModifier | None,
    deck_id: str = "classique",
    seed: int | None = None,
    ui_callbacks: RoundUICallbacks,
    target_score: int = 0,
    deck_list: list[int] | None = None,
    vouchers: list[Voucher] | None = None,
    acc: ScoreAccumulator | None = None,
) -> GameState:
    """
    Drive one complete Belote round through the classic engine.
    All scoring events are emitted to `bus`.
    The UI receives callbacks at each decision point.
    Returns the final GameState.
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    def _emit(event: object, s: GameState) -> GameState:
        bus.emit(event)
        if acc is not None:
            return acc.update_state(s, event)
        return s

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
        from belote.game import clear_legal_cards_cache
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

    # Bidding Phase
    while state.phase == Phase.BIDDING:
        bidder = state.turn
        if bidder == Seat.SOUTH:
            bid = ui_callbacks.prompt_bid(state)
        elif (
            bidder == Seat.NORTH
            and partner is not None
            and not partner.trust.ai_degraded
        ):
            # Use personality for the partner if trust is maintained
            if getattr(state, "_partner_forced_pass", False):
                bid = None
            elif partner.personality.should_bid(state):
                p_bid = partner.personality.bid_value(state)
                # Ensure the bid is legal for the current round
                forbidden = state.up_card.suit if state.up_card else None
                if state.bidding_round == 1:
                    # Round 1: Only taking the up-card's suit is legal
                    bid = forbidden if p_bid == forbidden else None
                else:
                    # Round 2: Only other suits are legal
                    bid = p_bid if p_bid != forbidden else None
            else:
                bid = None
        else:
            bid = ai_players[bidder].decide_bid(state)

        # Emit bid event for jokers
        state = _emit(
            BidMadeEvent(
                seat=bidder,
                trump=bid,
                contract="normal",  # Simplified for now
            ),
            state
        )
        state = process_bid(state, bid)

    if state.phase == Phase.DEAL:  # All passed
        return state

    # Play Phase
    while state.phase == Phase.PLAYING:
        player = state.turn
        if player == Seat.SOUTH:
            card, state = ui_callbacks.prompt_card(state)
        else:
            ai = ai_players[player]
            ai.update_memory(state)
            card = ai.decide_card(state)

        is_last_in_trick = len(state.current_trick) == 3
        old_pts_total = sum(state.current_round_points)
        state = play_card(state, card)

        ui_callbacks.on_card_played(state, player, card)

        if is_last_in_trick:
            last_trick = state.completed_tricks[-1]
            from belote.game import trick_winner_seat

            winner = trick_winner_seat(
                last_trick, state.trump, state._seven_eight_trump
            )
            # Use state diff to get points; perfectly handles all boss-aware points and Dix de Der
            points = sum(state.current_round_points) - old_pts_total

            # Emit declarations first if it's the first trick
            if len(state.completed_tricks) == 1:
                from belote.scoring import get_declaration_points
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

        if state.announced:
            # Handle Belote/Rebelote announcements
            state = _emit(
                BeloteAnnouncedEvent(seat=player, is_rebelote="Rebelote" in state.announced),
                state
            )
            state = clear_announced(state)

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
