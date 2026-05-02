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

        ui_callbacks.on_card_played(state, player, card)

        is_last_in_trick = len(state.current_trick) == 3
        state = play_card(state, card)

        if is_last_in_trick:
            last_trick = state.completed_tricks[-1]
            from belote.game import trick_winner_seat

            winner = trick_winner_seat(
                last_trick, state.trump, state._seven_eight_trump
            )
            # Boss-aware card points: Kings/10s may be 0, clubs tricks may score 0
            from belote.deck import Suit as _Suit
            if state._ban_clubs and last_trick and last_trick[0].card.suit == _Suit.CLUBS:
                points = 0
            else:
                points = sum(
                    0
                    if (state._kings_zero and c.card.rank == Rank.KING)
                    or (state._tens_zero and c.card.rank == Rank.TEN)
                    else card_points(c.card, state.trump, state._seven_eight_trump)
                    for c in last_trick
                )

            # Emit declarations first if it's the first trick
            if len(state.completed_tricks) == 1:
                for decl in state.declarations:
                    # In a full implementation, you'd get actual points, simplified here
                    state = _emit(
                        DeclarationScoredEvent(
                            seat=decl.seat,
                            declaration_type=decl.kind,
                            points=0,  # Would need proper point calculation
                        ),
                        state
                    )

            is_last = len(state.completed_tricks) == 8
            # Boss: Le Zéro Final – dix de der suppressed
            if is_last and not state._no_dix_de_der:
                points += 10  # Dix de Der

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
