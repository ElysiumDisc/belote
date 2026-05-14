"""M1 audit fix: tied carrés / sequences go to the first announcer.

Standard Belote-Coinché awards a tied declaration to the team whose seat
declared first. Announcement order starts at the taker and goes clockwise.
Pre-3.5.0 the resolver returned `scoring_team=None` (cancel) on any tie,
which was defensive but non-standard.
"""

from __future__ import annotations

from belote.deck import Card, Rank, Suit
from belote.game import Carre, Seat, Sequence
from belote.scoring import resolve_declarations

_RANK_VAL = {
    Rank.SEVEN: 1, Rank.EIGHT: 2, Rank.NINE: 3, Rank.TEN: 4,
    Rank.JACK: 5, Rank.QUEEN: 6, Rank.KING: 7, Rank.ACE: 8,
}


def _carre(rank: Rank) -> Carre:
    """Build a Carre at the given rank with four placeholder cards."""
    cards = tuple(
        Card(suit=s, rank=rank)
        for s in (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)
    )
    return Carre(rank=_RANK_VAL[rank], cards=cards)


def _sequence(length: int, top_rank: Rank, suit: Suit = Suit.SPADES) -> Sequence:
    return Sequence(
        length=length,
        top_rank=_RANK_VAL[top_rank],
        suit=suit,
        is_trump=False,
        cards=(),
    )


# ── Carrés ──────────────────────────────────────────────────────────────────


def test_carre_tie_without_taker_falls_back_to_cancel() -> None:
    """Legacy behaviour preserved when `taker` is not supplied."""
    same_carre = _carre(Rank.NINE)  # NS holds Carre of 9s
    other_carre = _carre(Rank.NINE)  # EW also Carre of 9s — identical strength
    decls = {
        Seat.SOUTH: {"sequences": [], "carres": [same_carre], "belote": False},
        Seat.EAST: {"sequences": [], "carres": [other_carre], "belote": False},
    }
    resolved = resolve_declarations(decls, trump=Suit.SPADES)  # no taker
    assert resolved.scoring_team is None


def test_carre_tie_goes_to_first_announcer_starting_from_taker() -> None:
    """Taker leads → declarations announced in taker, taker+1, taker+2, taker+3 order.
    The first seat in that order holding a matching carré wins the tie.
    """
    carre = _carre(Rank.NINE)
    # Taker = NORTH (NS). Announcement order: NORTH → EAST → SOUTH → WEST.
    # NS (NORTH) declares first → NS team wins the tie.
    decls = {
        Seat.NORTH: {"sequences": [], "carres": [carre], "belote": False},
        Seat.EAST: {"sequences": [], "carres": [carre], "belote": False},
    }
    resolved = resolve_declarations(decls, trump=Suit.SPADES, taker=Seat.NORTH)
    assert resolved.scoring_team == 0  # NS wins (NORTH declared first)


def test_carre_tie_first_announcer_can_be_east_team() -> None:
    """Same tie, taker = EAST → EAST declares first, EW wins."""
    carre = _carre(Rank.NINE)
    decls = {
        Seat.NORTH: {"sequences": [], "carres": [carre], "belote": False},
        Seat.EAST: {"sequences": [], "carres": [carre], "belote": False},
    }
    resolved = resolve_declarations(decls, trump=Suit.SPADES, taker=Seat.EAST)
    assert resolved.scoring_team == 1  # EW wins (EAST declared first)


def test_carre_strictly_higher_rank_still_wins() -> None:
    """Sanity: the tie-break only fires on equal rank; higher rank still wins outright."""
    ns_carre = _carre(Rank.JACK)  # carre of jacks (200 pts in non-TA)
    ew_carre = _carre(Rank.NINE)  # carre of nines (150 pts in trump-9, less elsewhere)
    decls = {
        Seat.SOUTH: {"sequences": [], "carres": [ns_carre], "belote": False},
        Seat.EAST: {"sequences": [], "carres": [ew_carre], "belote": False},
    }
    resolved = resolve_declarations(decls, trump=Suit.SPADES, taker=Seat.EAST)
    # Higher rank wins regardless of who announced first.
    assert resolved.scoring_team == 0  # NS


# ── Sequences ───────────────────────────────────────────────────────────────


def test_sequence_tie_without_taker_cancels() -> None:
    s = _sequence(length=3, top_rank=Rank.KING)
    decls = {
        Seat.SOUTH: {"sequences": [s], "carres": [], "belote": False},
        Seat.EAST: {"sequences": [s], "carres": [], "belote": False},
    }
    resolved = resolve_declarations(decls, trump=Suit.SPADES)
    assert resolved.scoring_team is None


def test_sequence_tie_goes_to_first_announcer() -> None:
    s = _sequence(length=3, top_rank=Rank.KING)
    decls = {
        Seat.NORTH: {"sequences": [s], "carres": [], "belote": False},
        Seat.EAST: {"sequences": [s], "carres": [], "belote": False},
    }
    # Taker = NORTH (NS) → NORTH declares first → NS wins.
    resolved = resolve_declarations(decls, trump=Suit.SPADES, taker=Seat.NORTH)
    assert resolved.scoring_team == 0
