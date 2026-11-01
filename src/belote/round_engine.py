"""One round of Belote, shared by every game mode.

`play_round` owns the phase order and the rules that connect the phases:

    bidding (with all-pass handling) → contract locked → tricks until scoring

Everything that differs between modes is a `RoundPolicy`: who decides bids
and cards (human prompt, AI, partner personality), what happens on an
all-pass (classic ends the round; BelAtro redeals), how coinche is resolved
for a locked contract, and what to show or record around each move. Classic
Belote (`gameflow.py`) and the BelAtro expansion (`belatro/engine/
round_driver.py`) are two policies over this one engine, so a rule change to
the round's flow lands once.

The engine is resumable: it starts from whatever phase `state` is in. Classic
undo hands it a restored mid-round state; the contract hook only runs when
bidding actually happened in this call, so undoing into the play phase never
re-asks for coinche.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Literal

from .deck import Card
from .game import BidValue, Phase, S, Seat, bidding_turn, play_card, process_bid


class RoundInterrupted(Exception):  # noqa: N818 - control-flow signal, not an error
    """Raised by a policy to abandon the round: the player quit, or asked to undo."""

    def __init__(self, reason: Literal["QUIT", "UNDO"]) -> None:
        super().__init__(reason)
        self.reason: Literal["QUIT", "UNDO"] = reason


class RoundPolicy(ABC, Generic[S]):
    """Mode-specific decisions and side effects for `play_round`.

    Only the two decision methods are required; every hook defaults to a
    no-op. Hooks that return a state may replace it (e.g. clearing a
    one-shot announcement); returning the argument unchanged is the norm.
    """

    @abstractmethod
    def choose_bid(self, state: S, seat: Seat) -> BidValue:
        """The bid `seat` makes now. May raise RoundInterrupted."""

    @abstractmethod
    def choose_card(self, state: S, seat: Seat) -> tuple[Card, S]:
        """The card `seat` plays now, plus the (possibly re-sorted) state.
        May raise RoundInterrupted."""

    def before_bid(self, state: S, seat: Seat, bid: BidValue) -> None:
        """The bid is decided but not yet applied."""

    def after_bid(self, state: S, seat: Seat) -> S:
        """The bid has been applied (`state` is the post-bid state)."""
        return state

    def on_all_pass(self, state: S) -> S | None:
        """Everyone passed both bidding rounds (`state.phase` is DEAL).

        Return a fresh deal in Phase.BIDDING to keep bidding, or None to end
        the round here (the engine returns the DEAL state).
        """
        return None

    def on_contract(self, state: S) -> S:
        """Bidding produced a contract; called once, before trick 1.
        Resolve coinche / surcoinche here (set `coinche_level`)."""
        return state

    def before_card(self, state: S, seat: Seat, card: Card) -> None:
        """The card is chosen but not yet applied (trick still open)."""

    def after_card(self, before: S, state: S, seat: Seat, card: Card) -> S:
        """The card has been applied; `before` is the pre-play state."""
        return state


def play_round(state: S, policy: RoundPolicy[S]) -> S:
    """Run the round from `state`'s current phase until it needs scoring
    (Phase.SCORING) or ends without a contract (Phase.DEAL)."""
    return play_tricks(play_bidding(state, policy), policy)


def play_bidding(state: S, policy: RoundPolicy[S]) -> S:
    """Bidding phase. Ends in PLAYING (contract locked, `on_contract` run),
    DEAL (all passed and the policy didn't redeal), or unchanged if `state`
    wasn't bidding."""
    bid_happened = False
    while state.phase == Phase.BIDDING:
        seat = bidding_turn(state)
        bid = policy.choose_bid(state, seat)
        policy.before_bid(state, seat, bid)
        state = policy.after_bid(process_bid(state, bid), seat)
        bid_happened = True
        if state.phase == Phase.DEAL:
            redeal = policy.on_all_pass(state)
            if redeal is None:
                return state
            state = redeal
    if bid_happened and state.phase == Phase.PLAYING and state.taker is not None:
        state = policy.on_contract(state)
    return state


def play_tricks(state: S, policy: RoundPolicy[S]) -> S:
    """Play phase: cards until the round needs scoring."""
    while state.phase == Phase.PLAYING:
        seat = state.turn
        card, state = policy.choose_card(state, seat)
        policy.before_card(state, seat, card)
        before = state
        state = policy.after_card(before, play_card(state, card), seat, card)
    return state
