from __future__ import annotations

from .deck import Card, Suit
from .game import (
    GameState,
    Phase,
    Seat,
    get_bidder,
    place_bid,
    play_card,
    legal_cards,
    trick_winner_seat,
)


def bidding_turn(state: GameState) -> Seat:
    """Return the seat whose turn it is to bid."""
    return get_bidder(state.dealer, state.bidder_index)


def process_bid(state: GameState, bid: Suit | None) -> GameState:
    """Process a bid and return the new state."""
    return place_bid(state, bid)


def run_bidding_round(
    state: GameState,
    bid_decisions: dict[Seat, Suit | None],
) -> GameState:
    """Run through all bidding turns using pre-decided bids."""
    current = state
    while current.phase == Phase.BIDDING:
        bidder = bidding_turn(current)
        bid = bid_decisions.get(bidder)
        if bid is None and bidder not in bid_decisions:
            break
        current = process_bid(current, bid_decisions.get(bidder))
    return current


def run_play_turn(state: GameState, card: Card) -> GameState:
    """Play a single card and advance state."""
    return play_card(state, card)


def is_round_complete(state: GameState) -> bool:
    """Check if the current round's play phase is complete."""
    return len(state.completed_tricks) >= 8


def is_game_over(state: GameState) -> bool:
    """Check if the game has ended (someone reached target score)."""
    ns, ew = state.team_scores
    return ns >= state.target or ew >= state.target


def winning_team(state: GameState) -> int | None:
    """Return 0 (NS) or 1 (EW) if game is over, else None."""
    ns, ew = state.team_scores
    if ns >= state.target and ew >= state.target:
        # Both crossed - taker wins if they succeeded, defenders if they failed
        # Simplified: higher score wins
        return 0 if ns >= ew else 1
    if ns >= state.target:
        return 0
    if ew >= state.target:
        return 1
    return None
