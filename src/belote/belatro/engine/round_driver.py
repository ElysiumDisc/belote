from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, card_points
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
) -> None:
    """
    Drive one complete Belote round through the classic engine.
    All scoring events are emitted to `bus`.
    The UI receives callbacks at each decision point.
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    # Initialize the base game state
    state = new_game(target=1000)  # Target doesn't matter for single round
    state = start_round(state, rng)

    # Simple AI players for the 3 other seats
    ai_players = {
        Seat.EAST: AIPlayer(Seat.EAST, Difficulty.MEDIUM),
        Seat.NORTH: AIPlayer(Seat.NORTH, Difficulty.MEDIUM),
        Seat.WEST: AIPlayer(Seat.WEST, Difficulty.MEDIUM),
    }

    # Bidding Phase
    while state.phase == Phase.BIDDING:
        bidder = state.turn
        if bidder == Seat.SOUTH:
            bid = ui_callbacks.prompt_bid(state)
        else:
            bid = ai_players[bidder].decide_bid(state)

        # Emit bid event for jokers
        bus.emit(
            BidMadeEvent(
                seat=bidder,
                trump=bid,
                contract="normal",  # Simplified for now
            )
        )
        state = process_bid(state, bid)

    if state.phase == Phase.DEAL:  # All passed
        return

    # Play Phase
    while state.phase == Phase.PLAYING:
        player = state.turn
        if player == Seat.SOUTH:
            card, state = ui_callbacks.prompt_card(state)
        else:
            ai = ai_players[player]
            ai.update_memory(state)
            card = ai.decide_card(state)

        ui_callbacks.on_card_played(state, player, card)

        is_last_in_trick = len(state.current_trick) == 3
        state = play_card(state, card)

        if is_last_in_trick:
            last_trick = state.completed_tricks[-1]
            from belote.game import trick_winner_seat

            winner = trick_winner_seat(
                last_trick, state.trump, getattr(state, "_seven_eight_trump", False)
            )
            points = sum(
                card_points(c.card, state.trump, getattr(state, "_seven_eight_trump", False))
                for c in last_trick
            )

            # Emit declarations first if it's the first trick
            if len(state.completed_tricks) == 1:
                for decl in state.declarations:
                    # In a full implementation, you'd get actual points, simplified here
                    bus.emit(
                        DeclarationScoredEvent(
                            seat=decl.seat,
                            declaration_type=decl.kind,
                            points=0,  # Would need proper point calculation
                        )
                    )

            is_last = len(state.completed_tricks) == 8
            if is_last:
                points += 10  # Dix de Der

            cards = tuple(tc.card for tc in last_trick)
            bus.emit(
                TrickWonEvent(
                    winner=winner,
                    cards=cards,
                    trick_number=len(state.completed_tricks),
                    is_last=is_last,
                    card_points=points,
                    trump=state.trump,
                )
            )

            ui_callbacks.on_trick_end(state, winner, points)

        if state.announced:
            # Handle Belote/Rebelote announcements
            bus.emit(BeloteAnnouncedEvent(seat=player, is_rebelote="Rebelote" in state.announced))
            state = clear_announced(state)

    # Round End / Scoring
    if state.phase == Phase.SCORING:
        breakdown = score_round(state)
        hand_remainder = tuple(state.hand_of(Seat.SOUTH))
        bus.emit(
            RoundEndEvent(
                breakdown=breakdown,
                taker_seat=state.taker,
                trump=state.trump,
                capot=is_capot(state) is not None,
                hand_remainder=hand_remainder,
            )
        )
        ui_callbacks.on_round_end(breakdown)
