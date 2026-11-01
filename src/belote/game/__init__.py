"""Core game rules. 4.11.0: split into a package.

    state.py    Seat, Phase, declarations, TrickCard, GameState, new_game
    legal.py    legal cards (memoised) and trick-winner rules
    bidding.py  dealing, bidding turn order, legal_bids, place_bid
    play.py     play_card: trick resolution, belote, live points
    sorting.py  hand ordering for display

Every name (including underscore helpers used by the AI, scoring and tests)
stays importable from `belote.game`. Transitions are pure: they take a state
and return a new one (`replace()` keeps an expansion's subclass).
"""

from __future__ import annotations

# Importable from `belote.game` before the split (callers rely on them).
from dataclasses import replace as replace

from ..deck import Card as Card
from ..deck import Contract as Contract
from ..deck import Rank as Rank
from ..deck import Suit as Suit
from .bidding import (
    _NORMAL_SUITS as _NORMAL_SUITS,
)
from .bidding import (
    _distribute_remaining_cards as _distribute_remaining_cards,
)
from .bidding import (
    bidding_turn as bidding_turn,
)
from .bidding import (
    deal_cards as deal_cards,
)
from .bidding import (
    get_bidder as get_bidder,
)
from .bidding import (
    legal_bids as legal_bids,
)
from .bidding import (
    place_bid as place_bid,
)
from .bidding import (
    process_bid as process_bid,
)
from .bidding import (
    shuffle_deck as shuffle_deck,
)
from .bidding import (
    start_round as start_round,
)
from .legal import (
    _CARD_TO_ID as _CARD_TO_ID,
)
from .legal import (
    _ID_TO_CARD as _ID_TO_CARD,
)
from .legal import (
    _NONTRUMP_RANK as _NONTRUMP_RANK,
)
from .legal import (
    _calculate_legal_cards_impl as _calculate_legal_cards_impl,
)
from .legal import (
    _card_beats as _card_beats,
)
from .legal import (
    _current_trick_winner as _current_trick_winner,
)
from .legal import (
    _trick_winner_seat_impl as _trick_winner_seat_impl,
)
from .legal import (
    clear_legal_cards_cache as clear_legal_cards_cache,
)
from .legal import (
    compute_trick_winners as compute_trick_winners,
)
from .legal import (
    legal_cards as legal_cards,
)
from .legal import (
    per_trick_trumps as per_trick_trumps,
)
from .legal import (
    trick_winner_seat as trick_winner_seat,
)
from .play import (
    _compute_live_round_points as _compute_live_round_points,
)
from .play import (
    _PlayContext as _PlayContext,
)
from .play import (
    _record_belote_announcement as _record_belote_announcement,
)
from .play import (
    _resolve_trick_winner as _resolve_trick_winner,
)
from .play import (
    _rotate_dynamic_trump as _rotate_dynamic_trump,
)
from .play import (
    clear_announced as clear_announced,
)
from .play import (
    play_card as play_card,
)
from .sorting import (
    _NORMAL_RANK_IDX as _NORMAL_RANK_IDX,
)
from .sorting import (
    _SUIT_IDX_CACHE as _SUIT_IDX_CACHE,
)
from .sorting import (
    _SUITS_ORDER as _SUITS_ORDER,
)
from .sorting import (
    _TRUMP_RANK_IDX as _TRUMP_RANK_IDX,
)
from .sorting import (
    _build_suit_idx as _build_suit_idx,
)
from .sorting import (
    sort_hand as sort_hand,
)
from .sorting import (
    sort_south_hand as sort_south_hand,
)
from .state import (
    SANS_ATOUT_BID as SANS_ATOUT_BID,
)
from .state import (
    BeloteDecl as BeloteDecl,
)
from .state import (
    BidValue as BidValue,
)
from .state import (
    Carre as Carre,
)
from .state import (
    Declaration as Declaration,
)
from .state import (
    GameState as GameState,
)
from .state import (
    IllegalMoveError as IllegalMoveError,
)
from .state import (
    Phase as Phase,
)
from .state import (
    RoundScore as RoundScore,
)
from .state import (
    S as S,
)
from .state import (
    Seat as Seat,
)
from .state import (
    Sequence as Sequence,
)
from .state import (
    TrickCard as TrickCard,
)
from .state import (
    new_game as new_game,
)
from .state import (
    partner as partner,
)
from .state import (
    reset_round_fields as reset_round_fields,
)
from .state import (
    team_of as team_of,
)
from .view import rotate_view as rotate_view
