"""Dealing and bidding: shuffle/deal, the bidding turn order, legal bids
and `place_bid` (which completes the deal and pre-computes declarations)."""

from __future__ import annotations

import random
from dataclasses import replace

from ..deck import Card, Contract, Rank, Suit, make_deck
from ..deck import deal as deal_cards_
from ..deck import shuffle as shuffle_deck_
from .state import (
    SANS_ATOUT_BID,
    BidValue,
    GameState,
    IllegalMoveError,
    Phase,
    S,
    Seat,
    reset_round_fields,
)


def start_round(state: S, rng: random.Random) -> S:
    """Deal cards and start bidding phase."""
    deck = shuffle_deck(rng)
    initial_hands, up_card, remaining = deal_cards(deck)
    dealer = state.dealer
    first_bidder = dealer.next_seat()  # bidding starts left of dealer

    return reset_round_fields(
        state,
        hands=initial_hands,
        initial_hands=initial_hands,
        leader=first_bidder,
        turn=first_bidder,
        phase=Phase.BIDDING,
        up_card=up_card,
        remaining_cards=remaining,
        bidding_round=1,
        belote_holders={},
        _rng=rng,
    )


def shuffle_deck(rng: random.Random) -> tuple[Card, ...]:
    return shuffle_deck_(make_deck(), rng)


def deal_cards(
    deck: tuple[Card, ...],
) -> tuple[tuple[tuple[Card, ...], ...], Card, tuple[Card, ...]]:
    return deal_cards_(deck)


def get_bidder(dealer: Seat, index: int) -> Seat:
    """Get the seat of the bidder at the given index."""
    start = dealer.next_seat()
    return Seat((start.value + index) % 4)


def bidding_turn(state: GameState) -> Seat:
    """Return the seat whose turn it is to bid."""
    return get_bidder(state.dealer, state.bidder_index)


def process_bid(state: S, bid: BidValue) -> S:
    """Process a bid and return the new state."""
    return place_bid(state, bid)


def _distribute_remaining_cards(state: GameState, taker: Seat) -> list[list[Card]]:
    """Helper to distribute remaining 11 cards after bidding is finished.
    Taker gets up-card + 2 more. Others get 3 more.
    """
    new_hands = [list(h) for h in state.hands]
    pool = list(state.remaining_cards)
    pool_idx = 0

    # Ordering: from dealer.next_seat() around the table (same as bidding order)
    for i in range(4):
        s = get_bidder(state.dealer, i)
        if s == taker:
            new_hands[s.value].append(state.up_card)  # type: ignore[arg-type]
            # Taker only needs 2 more
            new_hands[s.value].extend(pool[pool_idx : pool_idx + 2])
            pool_idx += 2
        else:
            # Others need 3 more
            new_hands[s.value].extend(pool[pool_idx : pool_idx + 3])
            pool_idx += 3

    if pool_idx != len(pool):
        raise ValueError(
            f"Deal corruption: {pool_idx} cards distributed from {len(pool)} available"
        )

    return new_hands


_NORMAL_SUITS: tuple[Suit, ...] = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)


def legal_bids(state: GameState) -> list[BidValue]:
    """Every bid the current bidder may make, in display order, pass last.

    Round 1: take the up-card suit, or pass.
    Round 2: any *other* normal suit, Tout Atout, Sans Atout, or pass.

    Single source of truth for the bid selector (prompt + render), the
    BelAtro joker hooks, and the partner-personality legality gate.
    """
    up_suit = state.up_card.suit if state.up_card is not None else None
    if state.bidding_round == 1:
        return [up_suit, None] if up_suit is not None else [None]
    others: list[BidValue] = [s for s in _NORMAL_SUITS if s != up_suit]
    return [*others, Suit.TOUT_ATOUT, SANS_ATOUT_BID, None]


def place_bid(state: S, bid: BidValue) -> S:
    """Process a bid from the current bidder.

    `bid` is one of:
    - `None` → pass
    - `Suit.SPADES`/`HEARTS`/`DIAMONDS`/`CLUBS` → normal contract
    - `Suit.TOUT_ATOUT` → Tout Atout (round 2 only)
    - `"sans_atout"` → Sans Atout (round 2 only)

    TA and SA in round 1 raise `IllegalMoveError` — round 1 is "take the
    up-card suit at the standard contract" only.
    """
    is_special = bid == Suit.TOUT_ATOUT or bid == SANS_ATOUT_BID
    if is_special and state.bidding_round == 1:
        raise IllegalMoveError("Tout Atout / Sans Atout can only be bid in round 2")

    new_bids = state.bids + (bid,)

    if bid is not None:
        # Someone chose trump
        taker = get_bidder(state.dealer, state.bidder_index)

        # Distribute remaining 11 cards
        new_hands = _distribute_remaining_cards(state, taker)

        if not all(len(h) == 8 for h in new_hands):
            raise ValueError(f"Deal corruption: Hands lengths {[len(h) for h in new_hands]}")

        # Map bid → (trump, contract). State.contract is the authoritative
        # contract identity; state.trump is the trump *suit* (None for SA, the
        # special TOUT_ATOUT marker for TA, a normal suit otherwise).
        if bid == SANS_ATOUT_BID:
            new_trump: Suit | None = None
            new_contract: str = Contract.SANS_ATOUT
        elif bid == Suit.TOUT_ATOUT:
            new_trump = Suit.TOUT_ATOUT
            new_contract = Contract.TOUT_ATOUT
        else:
            assert isinstance(bid, Suit)
            new_trump = bid
            new_contract = Contract.NORMAL

        # Pre-calculate belote holders. Belote = K+Q of trump. There is no
        # unique K+Q-of-trump under TA (every suit acts as trump) or SA (no
        # trump at all), so belote is disabled for both contracts. 3.6.0
        # (audit L1): single-pass per hand — previously rebuilt a set of all
        # (rank,suit) pairs then re-iterated 4 suits, 5× more work than
        # tracking which suits saw a King and which saw a Queen.
        belote_holders: dict[Suit, Seat] = {}
        if new_contract == Contract.NORMAL:
            for s_idx in range(4):
                seat = Seat(s_idx)
                king_suits: set[Suit] = set()
                queen_suits: set[Suit] = set()
                for c in new_hands[s_idx]:
                    if c.rank == Rank.KING:
                        king_suits.add(c.suit)
                    elif c.rank == Rank.QUEEN:
                        queen_suits.add(c.suit)
                # Suit order, not set order: set iteration follows the
                # per-process hash salt, which made the dict order (and so
                # repr/serialisation of seeded games) vary between runs.
                for suit in Suit:
                    if suit in king_suits and suit in queen_suits:
                        belote_holders[suit] = seat

        # Pre-calculate declarations
        from ..scoring import get_declarations

        # initial_hands stores the 8-card hands at start of play (not the 5-card deal),
        # used by score_round for declaration detection after cards are played out.
        temp_state = replace(
            state,
            hands=tuple(tuple(h) for h in new_hands),
            initial_hands=tuple(tuple(h) for h in new_hands),
            bids=new_bids,
            trump=new_trump,
            contract=new_contract,
            taker=taker,
            phase=Phase.PLAYING,
        )
        decls = get_declarations(temp_state)

        return replace(
            temp_state,
            leader=state.dealer.next_seat(),  # Standard: left of dealer leads
            turn=state.dealer.next_seat(),
            up_card=None,
            remaining_cards=(),
            belote_holders=belote_holders,
            declarations=decls,
        )
    # Pass
    next_index = state.bidder_index + 1
    if next_index >= 4:
        if state.bidding_round == 1:
            # Move to round 2
            return replace(
                state,
                bids=(),
                bidder_index=0,
                bidding_round=2,
                turn=state.dealer.next_seat(),
            )
        # All passed round 2 -> redeal
        return replace(
            state,
            bids=(),
            dealer=state.dealer.next_seat(),
            phase=Phase.DEAL,
            bidder_index=0,
            bidding_round=1,
        )
    next_bidder = get_bidder(state.dealer, next_index)
    return replace(
        state,
        bids=new_bids,
        turn=next_bidder,
        bidder_index=next_index,
    )
