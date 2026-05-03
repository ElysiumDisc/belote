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
    is_litige: bool = False
    litige_points: int = 0


@dataclass(frozen=True, slots=True)
class BossModifiers:
    """Boss-modifier flags injected by drive_round when a boss blind is active."""
    no_belote: bool = False
    dynamic_trump: bool = False
    no_consecutive_team_wins: bool = False
    seven_eight_trump: bool = False
    invert_scoring: bool = False
    kings_zero: bool = False
    auto_coinche: bool = False
    queen_spades_penalty: bool = False
    hide_hud: bool = False
    ban_clubs: bool = False
    no_dix_de_der: bool = False
    tens_zero: bool = False
    hide_partner_hand: bool = False
    agent_double_active: bool = False
    partner_forced_pass: bool = False
    lock_trust_zero: bool = False
    separate_scoring: bool = False


@dataclass(frozen=True, slots=True)
class GameState:
    hands: tuple[tuple[Card, ...], ...]
    initial_hands: tuple[tuple[Card, ...], ...] = field(default_factory=lambda: ((), (), (), ()))
    trump: Suit | None = None
    contract: str | None = None
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
    litige_points: int = 0
    
    boss_modifiers: BossModifiers = field(default_factory=BossModifiers)
    
    _joker_state: dict[str, object] = field(default_factory=dict)
    _chips: int = 0
    _mult: float = 1.0
    _bonus_money: int = 0

    @property
    def _no_belote(self) -> bool: return self.boss_modifiers.no_belote
    @property
    def _dynamic_trump(self) -> bool: return self.boss_modifiers.dynamic_trump
    @property
    def _no_consecutive_team_wins(self) -> bool: return self.boss_modifiers.no_consecutive_team_wins
    @property
    def _seven_eight_trump(self) -> bool: return self.boss_modifiers.seven_eight_trump
    @property
    def _invert_scoring(self) -> bool: return self.boss_modifiers.invert_scoring
    @property
    def _kings_zero(self) -> bool: return self.boss_modifiers.kings_zero
    @property
    def _auto_coinche(self) -> bool: return self.boss_modifiers.auto_coinche
    @property
    def _queen_spades_penalty(self) -> bool: return self.boss_modifiers.queen_spades_penalty
    @property
    def _hide_hud(self) -> bool: return self.boss_modifiers.hide_hud
    @property
    def _ban_clubs(self) -> bool: return self.boss_modifiers.ban_clubs
    @property
    def _no_dix_de_der(self) -> bool: return self.boss_modifiers.no_dix_de_der
    @property
    def _tens_zero(self) -> bool: return self.boss_modifiers.tens_zero
    @property
    def _hide_partner_hand(self) -> bool: return self.boss_modifiers.hide_partner_hand
    @property
    def _agent_double_active(self) -> bool: return self.boss_modifiers.agent_double_active
    @property
    def _partner_forced_pass(self) -> bool: return self.boss_modifiers.partner_forced_pass
    @property
    def _lock_trust_zero(self) -> bool: return self.boss_modifiers.lock_trust_zero
    @property
    def _separate_scoring(self) -> bool: return self.boss_modifiers.separate_scoring

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
        "boss_modifiers": BossModifiers(),
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


def process_bid(state: GameState, bid: Suit | None) -> GameState:
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


def place_bid(state: GameState, bid: Suit | None) -> GameState:
    """Process a bid from the current bidder."""
    new_bids = state.bids + (bid,)

    if bid is not None:
        # Someone chose trump
        taker = get_bidder(state.dealer, state.bidder_index)

        # Distribute remaining 11 cards
        new_hands = _distribute_remaining_cards(state, taker)

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
    _trick_winner_seat_impl.cache_clear()


def _calculate_legal_cards_impl(
    hand_ids: tuple[int, ...],
    trump: Suit | None,
    current_trick_ids: tuple[tuple[int, int], ...],
    seat_val: int,
    seven_eight_trump: bool = False,
) -> tuple[int, ...]:
    """Calculate legal cards using card IDs (memoized)."""
    # Map IDs back to Cards for logic
    hand = tuple(_ID_TO_CARD[i] for i in hand_ids)
    seat = Seat(seat_val)

    if trump is None:
        return hand_ids

    if not current_trick_ids:
        return hand_ids

    # Reconstruct TrickCard-like objects for the internal logic if needed,
    # but we can just use the IDs.
    lead_card_id = current_trick_ids[0][1]
    lead_card = _ID_TO_CARD[lead_card_id]
    lead_suit = lead_card.suit

    # Who is currently winning the trick?
    played_cards = [
        TrickCard(Seat(s), _ID_TO_CARD[c]) for s, c in current_trick_ids if s != seat_val
    ]

    current_winner = _current_trick_winner(played_cards, trump, lead_suit, seven_eight_trump)
    partner_winning = current_winner is not None and partner(seat) == current_winner

    my_suit_cards = [c for c in hand if c.suit == lead_suit]

    res_cards: tuple[Card, ...] = ()
    is_trump_lead = (lead_suit == trump) or (
        seven_eight_trump and lead_card.rank in (Rank.SEVEN, Rank.EIGHT)
    )

    if is_trump_lead:
        # Trump led: must follow if possible, must overtrump if possible
        if my_suit_cards:
            highest_in_trick = max(
                (trick_rank(tc.card, trump, seven_eight_trump) for tc in played_cards), default=-1
            )
            must_overtrump = any(
                trick_rank(c, trump, seven_eight_trump) > highest_in_trick for c in my_suit_cards
            )
            if must_overtrump:
                res_cards = tuple(
                    c
                    for c in my_suit_cards
                    if trick_rank(c, trump, seven_eight_trump) > highest_in_trick
                )
            else:
                res_cards = tuple(my_suit_cards)
        else:
            # Void in trump (led suit) - can only play non-trump
            res_cards = tuple(
                c
                for c in hand
                if c.suit != trump
                and not (seven_eight_trump and c.rank in (Rank.SEVEN, Rank.EIGHT))
            )
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
                my_trumps = [
                    c
                    for c in hand
                    if c.suit == trump or (seven_eight_trump and c.rank in (Rank.SEVEN, Rank.EIGHT))
                ]
                if my_trumps:
                    # Must trump; also must overtrump if possible
                    highest_trump_in_trick = max(
                        (
                            trick_rank(tc.card, trump, seven_eight_trump)
                            for tc in played_cards
                            if tc.card.suit == trump
                            or (seven_eight_trump and tc.card.rank in (Rank.SEVEN, Rank.EIGHT))
                        ),
                        default=-1,
                    )
                    can_overtrump = any(
                        trick_rank(c, trump, seven_eight_trump) > highest_trump_in_trick
                        for c in my_trumps
                    )
                    if can_overtrump:
                        res_cards = tuple(
                            c
                            for c in my_trumps
                            if trick_rank(c, trump, seven_eight_trump) > highest_trump_in_trick
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
    trick_ids = tuple((tc.seat.value, _CARD_TO_ID[tc.card]) for tc in state.current_trick)
    se_trump = state.boss_modifiers.seven_eight_trump

    res_ids = _calculate_legal_cards_impl(hand_ids, state.trump, trick_ids, seat.value, se_trump)

    return tuple(_ID_TO_CARD[i] for i in res_ids)


def _current_trick_winner(
    played: list[TrickCard], trump: Suit, lead_suit: Suit, seven_eight_trump: bool = False
) -> Seat | None:
    """Determine who is currently winning the trick based on cards played so far."""
    if not played:
        return None
    best = played[0]
    for tc in played[1:]:
        if _card_beats(tc.card, best.card, trump, lead_suit, seven_eight_trump):
            best = tc
    return best.seat


def _card_beats(
    card: Card, current_best: Card, trump: Suit, lead_suit: Suit, seven_eight_trump: bool = False
) -> bool:
    """Does card beat current_best?"""
    if card.suit == current_best.suit:
        return trick_rank(card, trump, seven_eight_trump) > trick_rank(
            current_best, trump, seven_eight_trump
        )

    # Lead card is usually the first card in the trick.
    # We need to know if the LEAD was a trump (declared or 7/8 in Deluge).
    is_trump_card = (card.suit == trump) or (
        seven_eight_trump and card.rank in (Rank.SEVEN, Rank.EIGHT)
    )
    is_best_trump = (current_best.suit == trump) or (
        seven_eight_trump and current_best.rank in (Rank.SEVEN, Rank.EIGHT)
    )

    if is_trump_card and not is_best_trump:
        return True
    if not is_trump_card and is_best_trump:
        return False

    # Neither are trump (or both are trump but different suits - only possible with 7/8 deluge)
    if is_trump_card and is_best_trump:
        # Both act as trumps, compare their trick_ranks
        return trick_rank(card, trump, seven_eight_trump) > trick_rank(
            current_best, trump, seven_eight_trump
        )

    return card.suit == lead_suit


def trick_winner_seat(
    trick: tuple[TrickCard, ...], trump: Suit | None, seven_eight_trump: bool = False
) -> Seat | None:
    """Determine the winner of a completed trick."""
    if not trick or trump is None:
        return None

    # Use a primitive-only key for memoization
    trick_ids = tuple((tc.seat.value, _CARD_TO_ID[tc.card]) for tc in trick)
    return _trick_winner_seat_impl(trick_ids, trump, seven_eight_trump)


@lru_cache(maxsize=1024)
def _trick_winner_seat_impl(
    trick_ids: tuple[tuple[int, int], ...], trump: Suit, seven_eight_trump: bool = False
) -> Seat:
    """Internal memoized winner detection using primitives."""
    # Convert back to TrickCard for existing logic or just use IDs
    # Existing logic uses _current_trick_winner which uses _card_beats
    played = [TrickCard(Seat(s), _ID_TO_CARD[c]) for s, c in trick_ids]
    lead_suit = played[0].card.suit

    # We can optimize this further by avoiding reconstruction if we rewrite _current_trick_winner
    # but for now this fixes the cache effectiveness while keeping logic central.
    res = _current_trick_winner(played, trump, lead_suit, seven_eight_trump)
    assert res is not None  # Should not be None if trick_ids is not empty
    return res


def play_card(state: GameState, card: Card) -> GameState:
    """Play a card. Returns new state, possibly advancing trick/round/phase."""
    legal = legal_cards(state, state.turn)
    if card not in legal:
        raise IllegalMoveError(f"Card {card} is not a legal move for {state.turn.name}")

    t = state.turn.value
    old_hand = state.hands[t]
    idx = old_hand.index(card)
    new_hand = old_hand[:idx] + old_hand[idx + 1 :]
    new_hands = state.hands[:t] + (new_hand,) + state.hands[t + 1 :]

    new_trick = state.current_trick + (TrickCard(state.turn, card),)

    # Check for belote/rebelote announcements; reset each play so popup fires only once
    announced = None
    trump = state.trump  # always set during PLAYING phase
    belote_tracker = list(state.belote_tracker)
    if trump and state.belote_holders.get(trump) == state.turn and not state.boss_modifiers.no_belote:
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
        se_trump = state.boss_modifiers.seven_eight_trump
        winner = trick_winner_seat(new_trick, trump, se_trump)

        # Boss: La Rupture (No consecutive team wins)
        if state.boss_modifiers.no_consecutive_team_wins and state.completed_tricks:
            last_winner = trick_winner_seat(state.completed_tricks[-1], trump, se_trump)
            if last_winner and winner and team_of(winner) == team_of(last_winner):
                # Force the other team to win if they had any card in the trick
                # or just pick the highest card of the other team.
                # Simplified Balatro-style boss: the current winner's team is penalized.
                # Actually, let's just pick the best card from the other team.
                other_team_cards = [
                    tc for tc in new_trick if team_of(tc.seat) != team_of(last_winner)
                ]
                if other_team_cards and trump:
                    # Find best card among other team
                    best_other = _current_trick_winner(
                        other_team_cards, trump, new_trick[0].card.suit, se_trump
                    )
                    if best_other:
                        winner = best_other

        if winner is None:
            winner = state.turn.prev_seat()

        new_completed = state.completed_tricks + (new_trick,)
        tricks_count = len(new_completed)

        # Update current round points
        trick_pts = (
            sum(card_points(tc.card, trump, se_trump) for tc in new_trick)
            if trump is not None
            else 0
        )
        # Boss: Les Clubs Bannis – club-led tricks score 0
        if state.boss_modifiers.ban_clubs and new_trick and new_trick[0].card.suit == Suit.CLUBS:
            trick_pts = 0
        # Boss: Le Roi Mort / Les Dix Maudits – Kings/10s worth 0
        if state.boss_modifiers.kings_zero or state.boss_modifiers.tens_zero:
            trick_pts = sum(
                0
                if (state.boss_modifiers.kings_zero and tc.card.rank == Rank.KING)
                or (state.boss_modifiers.tens_zero and tc.card.rank == Rank.TEN)
                else card_points(tc.card, trump, se_trump)
                for tc in new_trick
            ) if trump is not None else 0
        ns_pts, ew_pts = state.current_round_points
        if team_of(winner) == 0:
            ns_pts += trick_pts
        else:
            ew_pts += trick_pts

        # Last trick bonus (suppressed by Le Zéro Final boss)
        if tricks_count == 8 and not state.boss_modifiers.no_dix_de_der:
            if team_of(winner) == 0:
                ns_pts += 10
            else:
                ew_pts += 10

        new_round_points = (ns_pts, ew_pts)

        # Boss: L'Anarchie (Trump changes every 2 tricks)
        current_trump = trump
        if state.boss_modifiers.dynamic_trump and tricks_count % 2 == 0 and tricks_count < 8:
            possible = [s for s in Suit if s != trump]
            current_trump = random.choice(possible)
            # Use set_announced to notify user?
            # For now we'll just update it quietly, maybe add a message.

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
                trump=current_trump,
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
            trump=current_trump,
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


_SUITS_ORDER: Final = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
_TRUMP_RANK_IDX: Final = {
    r: i
    for i, r in enumerate(
        [
            Rank.JACK,
            Rank.NINE,
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
    )
}
_NORMAL_RANK_IDX: Final = {
    r: i
    for i, r in enumerate(
        [
            Rank.ACE,
            Rank.TEN,
            Rank.KING,
            Rank.QUEEN,
            Rank.JACK,
            Rank.NINE,
            Rank.EIGHT,
            Rank.SEVEN,
        ]
    )
}


def sort_hand(hand: tuple[Card, ...], trump: Suit | None) -> tuple[Card, ...]:
    """Sort hand by suit and rank (trump first, then others, honors together)."""
    suits_order = list(_SUITS_ORDER)
    if trump:
        suits_order.remove(trump)
        suits_order.insert(0, trump)

    suit_idx = {s: i for i, s in enumerate(suits_order)}

    def sort_key(c: Card) -> tuple[int, int]:
        return (
            suit_idx[c.suit],
            _TRUMP_RANK_IDX[c.rank] if c.suit == trump else _NORMAL_RANK_IDX[c.rank],
        )

    return tuple(sorted(hand, key=sort_key))


def sort_south_hand(state: GameState) -> GameState:
    """Sort South's hand and update state."""
    new_hands = list(state.hands)
    new_hands[Seat.SOUTH.value] = sort_hand(state.hands[Seat.SOUTH.value], state.trump)

    new_initial = list(state.initial_hands)
    if new_initial[Seat.SOUTH.value]:
        new_initial[Seat.SOUTH.value] = sort_hand(
            state.initial_hands[Seat.SOUTH.value], state.trump
        )

    return replace(state, hands=tuple(new_hands), initial_hands=tuple(new_initial))

