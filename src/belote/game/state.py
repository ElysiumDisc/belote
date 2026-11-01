"""Game state and its vocabulary: seats, phases, declarations, tricks,
`GameState` itself and the generic `reset_round_fields` / `new_game`."""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Literal, TypeVar

from ..deck import Card, Suit
from ..variants import RuleVariants

# Transitions are generic over GameState subclasses: `replace()` keeps the
# concrete type, so an expansion's state subclass round-trips unchanged.
S = TypeVar("S", bound="GameState")

# Sentinel for the Sans Atout contract at the bidding API boundary.
# `Suit.TOUT_ATOUT` already exists for Tout Atout. Sans Atout has no card-suit
# equivalent (no card has this "suit"), so the bid value is the string literal
# `"sans_atout"`. Post-bid this is encoded as `state.trump=None` plus
# `state.contract="sans_atout"` — `state.contract` is the authoritative carrier
# of contract identity from PLAYING onward.
SANS_ATOUT_BID: Literal["sans_atout"] = "sans_atout"
BidValue = Suit | Literal["sans_atout"] | None

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
    contract: str | None = None
    trump: Suit | None = None
    taker_seat: Seat | None = None
    tricks_ns: int = 0
    tricks_ew: int = 0
    last_trick_winner: Seat | None = None
    decl_summary_ns: tuple[str, ...] = ()
    decl_summary_ew: tuple[str, ...] = ()


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
    bids: tuple[BidValue, ...] = field(default_factory=tuple)
    taker: Seat | None = None
    current_trick: tuple[TrickCard, ...] = field(default_factory=tuple)
    completed_tricks: tuple[tuple[TrickCard, ...], ...] = field(default_factory=tuple)
    # Trump in force when each completed trick was played (aligned with
    # `completed_tricks`). Only differs from `trump` under L'Anarchie
    # (`dynamic_trump`), which rotates trump every 2 tricks; final scoring must
    # resolve each trick with the trump it was actually played under.
    trick_trumps: tuple[Suit | None, ...] = field(default_factory=tuple)
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
    announced: str | None = None
    # Mutable dict held inside a `frozen=True` GameState. Contract: always
    # rebuild via `dataclasses.replace(state, belote_holders=new_dict)` —
    # never mutate in place. The `frozen` guarantee covers the field
    # reference, not the dict contents.
    belote_holders: dict[Suit, Seat] = field(default_factory=dict)
    belote_tracker: tuple[bool, bool] = (False, False)
    # Set when belote_tracker[0] first flips True — captures *which seat*
    # announced belote at the moment of announcement. Needed because the
    # L'Anarchie boss rotates state.trump mid-round, which would otherwise
    # make the scoring-side `belote_holders.get(state.trump)` lookup return
    # the wrong seat (or None) for a belote that was announced on the
    # original trump.
    belote_announcer: Seat | None = None
    # Captured at the same moment as `belote_announcer` — the trump suit at
    # the time belote was first announced. Under L'Anarchie (`dynamic_trump`)
    # `state.trump` rotates every 2 tricks, so the K/Q played second may not
    # match the *current* trump when scoring fires; we match against the
    # captured original trump instead. None outside a belote window.
    belote_trump: Suit | None = None
    first_trick_done: bool = False
    litige_points: int = 0
    # 4.9.0 / G1: 0 = normal, 1 = coinched (×2), 2 = surcoinched (×4).
    # Set by the post-bid coinche flow in `gameflow.py::run_bidding`. Applied
    # to the winning team's credit in `scoring.py::apply_round_score`.
    coinche_level: int = 0

    variants: RuleVariants = field(default_factory=RuleVariants)

    # Expansions extend GameState by subclassing (see belatro/core/state.py).
    # Every transition below builds the next state with `replace()`, which
    # preserves the subclass, so extension fields ride along untouched.
    _rng: random.Random = field(default_factory=random.Random, compare=False, repr=False)

    def hand_of(self, seat: Seat) -> tuple[Card, ...]:
        return self.hands[seat.value]


# ---------------------------------------------------------------------------
# Pure transitions
# ---------------------------------------------------------------------------


def reset_round_fields(state: S, **kwargs: object) -> S:
    """Return a new state with round-specific fields reset to defaults.

    `litige_points` is deliberately NOT reset here. The litige pool survives
    across rounds — including all-pass redeals — until a non-litige scoring
    round consumes it (see `scoring.py::apply_round_score`). Tests in
    `tests/test_bidding_all_pass.py` pin this contract.
    """
    reset_values: dict[str, object] = {
        "trump": None,
        "taker": None,
        "current_trick": (),
        "completed_tricks": (),
        "trick_trumps": (),
        "last_trick_winner": None,
        "bids": (),
        "bidder_index": 0,
        "current_round_points": (0, 0),
        "declarations": (),
        "announced": None,
        "belote_tracker": (False, False),
        "belote_announcer": None,
        "belote_trump": None,
        "first_trick_done": False,
        "variants": RuleVariants(),
        # 4.9.0 / G1: coinche state is per-round, reset to neutral.
        "coinche_level": 0,
    }
    reset_values.update(kwargs)
    return replace(state, **reset_values)  # type: ignore[arg-type]


def new_game(target: int = 1000) -> GameState:
    return GameState(
        hands=((), (), (), ()),
        target=target,
    )
