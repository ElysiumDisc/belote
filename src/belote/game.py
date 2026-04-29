from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from enum import Enum
from functools import lru_cache
from typing import Final, Literal

from .deck import Card, Rank, Suit, card_points, make_deck, trick_rank
from .deck import deal as deal_cards_
from .deck import shuffle as shuffle_deck_

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Phase(Enum):
    DEAL = "DEAL"
    BIDDING = "BIDDING"
    PLAYING = "PLAYING"
    SCORING = "SCORING"
    GAME_OVER = "GAME_OVER"


class IllegalMoveError(Exception):
    """Raised when a player attempts an illegal play."""
    pass


class Seat(Enum):
    SOUTH = 0
    EAST = 1
    NORTH = 2
    WEST = 3

    def next_seat(self) -> Seat:
        return Seat((self.value + 1) % 4)

    def prev_seat(self) -> Seat:
        return Seat((self.value - 1) % 4)

    @property
    def name(self) -> str:
        match self:
            case Seat.SOUTH:
                return "South"
            case Seat.EAST:
                return "East"
            case Seat.NORTH:
                return "North"
            case Seat.WEST:
                return "West"

    @property
    def label(self) -> str:
        if self == Seat.SOUTH:
            return "You"
        return self.name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def team_of(seat: Seat) -> int:
    """0 = NS, 1 = EW."""
    return 0 if seat in (Seat.SOUTH, Seat.NORTH) else 1


def partner(seat: Seat) -> Seat:
    if seat == Seat.SOUTH:
        return Seat.NORTH
    if seat == Seat.NORTH:
        return Seat.SOUTH
    if seat == Seat.EAST:
        return Seat.WEST
    return Seat.EAST


# ---------------------------------------------------------------------------
# Declaration types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Sequence:
    length: int
    top_rank: int  # numeric rank value (higher = better)
    suit: Suit
    is_trump: bool
    cards: tuple[Card, ...]


@dataclass(frozen=True, slots=True)
class Carre:
    rank: int  # numeric rank value
    cards: tuple[Card, ...]


@dataclass(frozen=True, slots=True)
class BeloteDecl:
    cards: tuple[Card, ...]  # K+Q of trump


@dataclass(frozen=True, slots=True)
class Declaration:
    seat: Seat
    kind: Literal["belote", "rebelote", "sequence", "carre"]
    detail: Sequence | Carre | BeloteDecl | None = None


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TrickCard:
    seat: Seat
    card: Card


@dataclass(frozen=True, slots=True)
class RoundScore:
    taker_team: int
    ns_card_pts: int
    ew_card_pts: int
    ns_decl_pts: int
    ew_decl_pts: int
    ns_belote_pts: int
    ew_belote_pts: int
    ns_rebelote: bool
    ew_rebelote: bool
    ns_total: int
    ew_total: int
    is_failed: bool
    is_capot: bool


@dataclass(frozen=True, slots=True)
class GameState:
    hands: tuple[tuple[Card, ...], ...]
    initial_hands: tuple[tuple[Card, ...], ...] = field(default_factory=lambda: ((), (), (), ()))
    trump: Suit | None = None
    dealer: Seat = Seat.SOUTH
    leader: Seat = Seat.SOUTH
    turn: Seat = Seat.SOUTH
    phase: Phase = Phase.DEAL
    bids: tuple[Suit | None, ...] = field(default_factory=tuple)
    taker: Seat | None = None
    current_trick: tuple[TrickCard, ...] = field(default_factory=tuple)
    completed_tricks: tuple[tuple[TrickCard, ...], ...] = field(default_factory=tuple)
    last_trick_winner: Seat | None = None
    declarations: tuple[Declaration, ...] = field(default_factory=tuple)
    team_scores: tuple[int, int] = (0, 0)
    current_round_points: tuple[int, int] = (0, 0)
    score_history: tuple[RoundScore, ...] = field(default_factory=tuple)
    target: int = 1000
    up_card: Card | None = None
    remaining_cards: tuple[Card, ...] = field(default_factory=tuple)
    bidder_index: int = 0
    bidding_round: int = 1
    bid_suits: tuple[Suit, ...] = field(default_factory=tuple)
    announced: str | None = None
    belote_holders: dict[Suit, Seat] = field(default_factory=dict)
    belote_tracker: tuple[bool, bool] = (False, False)
    first_trick_done: bool = False
    def hand_of(self, seat: Seat) -> tuple[Card, ...]:
        return self.hands[seat.value]

    @property
    def current_bidder(self) -> Seat:
        return get_bidder(self.dealer, self.bidder_index)

# ---------------------------------------------------------------------------
# Pure transitions
# ---------------------------------------------------------------------------

def reset_round_fields(state: GameState, **kwargs: object) -> GameState:
    """Return a new state with round-specific fields reset to defaults."""
    reset_values: dict[str, object] = {
        "trump": None,
        "taker": None,
        "current_trick": (),
        "completed_tricks": (),
        "last_trick_winner": None,
        "bids": (),
        "bidder_index": 0,
        "bid_suits": (),
        "current_round_points": (0, 0),
        "declarations": (),
        "announced": None,
        "belote_tracker": (False, False),
        "first_trick_done": False,
    }
    reset_values.update(kwargs)
    return replace(state, **reset_values)  # type: ignore[arg-type]


def new_game(target: int = 1000) -> GameState:
    return GameState(
        hands=((), (), (), ()),
        target=target,
    )


def start_round(state: GameState, rng: random.Random) -> GameState:
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
    )


def shuffle_deck(rng: random.Random) -> tuple[Card, ...]:
    return shuffle_deck_(make_deck(), rng)


def deal_cards(deck: tuple[Card, ...]) -> tuple[tuple[tuple[Card, ...], ...], Card, tuple[Card, ...]]:
    return deal_cards_(deck)


def get_bidder(dealer: Seat, index: int) -> Seat:
    """Get the seat of the bidder at the given index."""
    start = dealer.next_seat()
    return Seat((start.value + index) % 4)


def bidding_turn(state: GameState) -> Seat:
    """Return the seat whose turn it is to bid."""
    return get_bidder(state.dealer, state.bidder_index)


def process_bid(state: GameState, bid: Suit | None) -> GameState:
    """Process a bid and return the new state."""
    return place_bid(state, bid)


def place_bid(state: GameState, bid: Suit | None) -> GameState:
    """Process a bid from the current bidder."""
    new_bids = state.bids + (bid,)

    if bid is not None:
        # Someone chose trump
        taker = get_bidder(state.dealer, state.bidder_index)

        # Distribute remaining 11 cards
        new_hands = [list(h) for h in state.hands]
        pool = list(state.remaining_cards)
        pool_idx = 0

        # Ordering: from dealer.next_seat() around the table
        for i in range(4):
            s = get_bidder(state.dealer, i)
            if s == taker:
                new_hands[s.value].append(state.up_card) # type: ignore[arg-type]
                # Taker only needs 2 more
                new_hands[s.value].extend(pool[pool_idx:pool_idx+2])
                pool_idx += 2
            else:
                # Others need 3 more
                new_hands[s.value].extend(pool[pool_idx:pool_idx+3])
                pool_idx += 3

        if pool_idx != len(pool):
            raise ValueError(f"Deal corruption: {pool_idx} cards distributed from {len(pool)} available")
        if not all(len(h) == 8 for h in new_hands):
            raise ValueError(f"Deal corruption: Hands lengths {[len(h) for h in new_hands]}")

        # Pre-calculate belote holders
        belote_holders = {}
        for s_idx in range(4):
            seat = Seat(s_idx)
            hand = new_hands[s_idx]
            hand_set = {(c.rank, c.suit) for c in hand}
            for suit in Suit:
                if (Rank.KING, suit) in hand_set and (Rank.QUEEN, suit) in hand_set:
                    belote_holders[suit] = seat

        # Pre-calculate declarations
        from .scoring import get_declarations
        # initial_hands stores the 8-card hands at start of play (not the 5-card deal),
        # used by score_round for declaration detection after cards are played out.
        temp_state = replace(
            state,
            hands=tuple(tuple(h) for h in new_hands),
            initial_hands=tuple(tuple(h) for h in new_hands),
            bids=new_bids,
            trump=bid,
            taker=taker,
            phase=Phase.PLAYING,
        )
        decls = get_declarations(temp_state)

        return replace(
            temp_state,
            leader=state.dealer.next_seat(), # Standard: left of dealer leads
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
            bid_suits=(),
        )
    next_bidder = get_bidder(state.dealer, next_index)
    return replace(
        state,
        bids=new_bids,
        turn=next_bidder,
        bidder_index=next_index,
    )


# ---------------------------------------------------------------------------
# Trick play / caching
# ---------------------------------------------------------------------------

_CARD_TO_ID: Final = {c: i for i, c in enumerate(make_deck())}
_ID_TO_CARD: Final = {v: k for k, v in _CARD_TO_ID.items()}


def clear_legal_cards_cache() -> None:
    """Clear the legal cards cache."""
    _calculate_legal_cards_impl.cache_clear()
    trick_winner_seat.cache_clear()


@lru_cache(maxsize=2048)
def _calculate_legal_cards_impl(
    hand_ids: tuple[int, ...],
    trump: Suit | None,
    current_trick: tuple[TrickCard, ...],
    seat: Seat,
) -> tuple[int, ...]:
    """Calculate legal cards using card IDs (memoized)."""
    # Map IDs back to Cards for logic
    hand = tuple(_ID_TO_CARD[i] for i in hand_ids)

    if trump is None:
        return hand_ids

    if not current_trick:
        return hand_ids

    lead_card = current_trick[0].card
    lead_suit = lead_card.suit

    # Check what cards have been played
    played_cards = [tc for tc in current_trick if tc.seat != seat]

    # Determine who is currently winning the trick
    current_winner = _current_trick_winner(played_cards, trump, lead_suit)
    partner_winning = current_winner is not None and partner(seat) == current_winner

    my_suit_cards = [c for c in hand if c.suit == lead_suit]

    res_cards: tuple[Card, ...] = ()
    if lead_suit == trump:
        # Trump led: must follow if possible, must overtrump if possible
        if my_suit_cards:
            highest_in_trick = max(
                (trick_rank(tc.card, trump) for tc in played_cards),
                default=-1
            )
            must_overtrump = any(
                trick_rank(c, trump) > highest_in_trick for c in my_suit_cards
            )
            if must_overtrump:
                res_cards = tuple(c for c in my_suit_cards if trick_rank(c, trump) > highest_in_trick)
            else:
                res_cards = tuple(my_suit_cards)
        else:
            # Void in trump (led suit) - can only play non-trump
            res_cards = tuple(c for c in hand if c.suit != trump)
    else:
        # Non-trump led
        if my_suit_cards:
            # Must follow suit
            res_cards = tuple(my_suit_cards)
        else:
            # Void in led suit
            if partner_winning:
                # Partner is winning - can discard
                res_cards = hand
            else:
                # Must trump if possible
                my_trumps = [c for c in hand if c.suit == trump]
                if my_trumps:
                    # Must trump; also must overtrump if possible
                    highest_trump_in_trick = max(
                        (trick_rank(tc.card, trump) for tc in played_cards if tc.card.suit == trump),
                        default=-1,
                    )
                    can_overtrump = any(
                        trick_rank(c, trump) > highest_trump_in_trick for c in my_trumps
                    )
                    if can_overtrump:
                        res_cards = tuple(
                            c for c in my_trumps
                            if trick_rank(c, trump) > highest_trump_in_trick
                        )
                    else:
                        res_cards = tuple(my_trumps)
                else:
                    # Can't follow, can't trump - discard
                    res_cards = hand

    return tuple(_CARD_TO_ID[c] for c in res_cards)


def legal_cards(state: GameState, seat: Seat) -> tuple[Card, ...]:
    """Return the set of legal cards for the given seat to play (memoized)."""
    if state.phase != Phase.PLAYING:
        return state.hand_of(seat)

    hand = state.hand_of(seat)
    hand_ids = tuple(_CARD_TO_ID[c] for c in hand)

    res_ids = _calculate_legal_cards_impl(
        hand_ids,
        state.trump,
        state.current_trick,
        seat
    )

    return tuple(_ID_TO_CARD[i] for i in res_ids)


def _current_trick_winner(
    played: list[TrickCard], trump: Suit, lead_suit: Suit
) -> Seat | None:
    """Determine who is currently winning the trick based on cards played so far."""
    if not played:
        return None
    best = played[0]
    for tc in played[1:]:
        if _card_beats(tc.card, best.card, trump, lead_suit):
            best = tc
    return best.seat


def _card_beats(card: Card, current_best: Card, trump: Suit, lead_suit: Suit) -> bool:
    """Does card beat current_best?"""
    if card.suit == current_best.suit:
        return trick_rank(card, trump) > trick_rank(current_best, trump)

    if lead_suit == trump:
        # Trump led; current_best.suit cannot be trump (handled by first check)
        return card.suit == trump
    # Non-trump led
    if card.suit == trump:
        return True
    if current_best.suit == trump:
        return False
    return card.suit == lead_suit


@lru_cache(maxsize=128)
def trick_winner_seat(trick: tuple[TrickCard, ...], trump: Suit | None) -> Seat | None:
    """Determine the winner of a completed trick."""
    if not trick or trump is None:
        return None
    lead_suit = trick[0].card.suit
    return _current_trick_winner(list(trick), trump, lead_suit)


def play_card(state: GameState, card: Card) -> GameState:
    """Play a card. Returns new state, possibly advancing trick/round/phase."""
    legal = legal_cards(state, state.turn)
    if card not in legal:
        raise IllegalMoveError(f"Card {card} is not a legal move for {state.turn.name}")

    t = state.turn.value
    old_hand = state.hands[t]
    idx = old_hand.index(card)
    new_hand = old_hand[:idx] + old_hand[idx + 1:]
    new_hands = state.hands[:t] + (new_hand,) + state.hands[t + 1:]

    new_trick = state.current_trick + (TrickCard(state.turn, card),)

    # Check for belote/rebelote announcements; reset each play so popup fires only once
    announced = None
    trump = state.trump  # always set during PLAYING phase
    belote_tracker = list(state.belote_tracker)
    if trump and state.belote_holders.get(trump) == state.turn:
        is_k_q = card.rank in (Rank.KING, Rank.QUEEN) and card.suit == trump

        if is_k_q:
            if not belote_tracker[0]:
                belote_tracker[0] = True
                announced = "Belote!"
            elif not belote_tracker[1]:
                belote_tracker[1] = True
                announced = "Rebelote!"

    # Check if trick is complete (4 cards)
    if len(new_trick) == 4:
        winner = trick_winner_seat(new_trick, trump)
        if winner is None:
            winner = state.turn

        new_completed = state.completed_tricks + (new_trick,)
        tricks_count = len(new_completed)

        # Update current round points
        trick_pts = sum(card_points(tc.card, trump) for tc in new_trick) if trump is not None else 0
        ns_pts, ew_pts = state.current_round_points
        if team_of(winner) == 0:
            ns_pts += trick_pts
        else:
            ew_pts += trick_pts

        # Last trick bonus
        if tricks_count == 8:
            if team_of(winner) == 0:
                ns_pts += 10
            else:
                ew_pts += 10

        new_round_points = (ns_pts, ew_pts)

        # Check if round is complete (8 tricks)
        if tricks_count >= 8:
            # Round over
            return replace(
                state,
                hands=tuple(new_hands),
                current_trick=(),
                completed_tricks=new_completed,
                last_trick_winner=winner,
                leader=winner,
                turn=winner,
                phase=Phase.SCORING,
                announced=announced,
                belote_tracker=(belote_tracker[0], belote_tracker[1]),
                first_trick_done=True,
                current_round_points=new_round_points,
            )
        # Next trick led by winner
        first_trick_done = state.first_trick_done or tricks_count >= 1
        return replace(
            state,
            hands=tuple(new_hands),
            current_trick=(),
            completed_tricks=new_completed,
            last_trick_winner=winner,
            leader=winner,
            turn=winner,
            phase=Phase.PLAYING,
            announced=announced,
            belote_tracker=(belote_tracker[0], belote_tracker[1]),
            first_trick_done=first_trick_done,
            current_round_points=new_round_points,
        )
    # Next player in trick
    next_turn = state.turn.next_seat()
    return replace(
        state,
        hands=tuple(new_hands),
        current_trick=new_trick,
        turn=next_turn,
        announced=announced,
        belote_tracker=(belote_tracker[0], belote_tracker[1]),
    )


def advance_turn(state: GameState) -> GameState:
    """Advance to the next player's turn (used after AI plays)."""
    return replace(state, turn=state.turn.next_seat())


def set_announced(state: GameState, msg: str) -> GameState:
    return replace(state, announced=msg)


def clear_announced(state: GameState) -> GameState:
    return replace(state, announced=None)


def sort_hand(hand: tuple[Card, ...], trump: Suit | None) -> tuple[Card, ...]:
    """Sort hand by suit and rank (trump first, then others, honors together)."""
    suits_order = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
    if trump:
        suits_order.remove(trump)
        suits_order.insert(0, trump)

    suit_idx = {s: i for i, s in enumerate(suits_order)}
    trump_rank_idx: dict[Rank, int] = {r: i for i, r in enumerate([
        Rank.JACK, Rank.NINE, Rank.ACE, Rank.TEN,
        Rank.KING, Rank.QUEEN, Rank.EIGHT, Rank.SEVEN,
    ])}
    normal_rank_idx: dict[Rank, int] = {r: i for i, r in enumerate([
        Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN,
        Rank.JACK, Rank.NINE, Rank.EIGHT, Rank.SEVEN,
    ])}

    def sort_key(c: Card) -> tuple[int, int]:
        return (suit_idx[c.suit], trump_rank_idx[c.rank] if c.suit == trump else normal_rank_idx[c.rank])

    return tuple(sorted(hand, key=sort_key))


def sort_south_hand(state: GameState) -> GameState:
    """Sort South's hand and update state."""
    new_hands = list(state.hands)
    new_hands[Seat.SOUTH.value] = sort_hand(state.hands[Seat.SOUTH.value], state.trump)

    new_initial = list(state.initial_hands)
    if new_initial[Seat.SOUTH.value]:
        new_initial[Seat.SOUTH.value] = sort_hand(state.initial_hands[Seat.SOUTH.value], state.trump)

    return replace(state, hands=tuple(new_hands), initial_hands=tuple(new_initial))
