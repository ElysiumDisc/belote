"""Declarations (annonces): sequences, carrés, belote — detection, the
per-team resolution of who scores them, and their point values."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TypedDict

from ..deck import Card, Contract, Rank, Suit
from ..game import (
    Carre,
    Declaration,
    GameState,
    Phase,
    Seat,
    Sequence,
    team_of,
)

# Rank numeric values for sequence detection (ascending order)
_RANK_VALUES: dict[Rank, int] = {
    Rank.SEVEN: 1,
    Rank.EIGHT: 2,
    Rank.NINE: 3,
    Rank.TEN: 4,
    Rank.JACK: 5,
    Rank.QUEEN: 6,
    Rank.KING: 7,
    Rank.ACE: 8,
}

_VALUE_TO_RANK: dict[int, Rank] = {v: r for r, v in _RANK_VALUES.items()}

# Carré point values
_CARRE_POINTS: dict[Rank, int] = {
    Rank.JACK: 200,
    Rank.NINE: 150,
    Rank.ACE: 100,
    Rank.TEN: 100,
    Rank.KING: 100,
    Rank.QUEEN: 100,
    Rank.SEVEN: 0,
    Rank.EIGHT: 0,
}

# Sequence point values
_SEQUENCE_POINTS: dict[int, int] = {
    3: 20,
    4: 50,
    5: 100,
}


def get_declaration_points(decls: list[Sequence | Carre]) -> int:
    """Calculate point value for a list of sequences or carres."""
    pts = 0
    for d in decls:
        if isinstance(d, Sequence):
            # 5+ cards is always a Quinte (100 pts)
            length = min(d.length, 5)
            pts += _SEQUENCE_POINTS.get(length, 0)
        elif isinstance(d, Carre):
            pts += _CARRE_POINTS.get(_VALUE_TO_RANK[d.rank], 0)
    return pts


@dataclass(frozen=True, slots=True)
class ResolvedDeclarations:
    ns_sequences: tuple[Sequence, ...]
    ew_sequences: tuple[Sequence, ...]
    ns_carres: tuple[Carre, ...]
    ew_carres: tuple[Carre, ...]
    ns_belote: bool
    ew_belote: bool
    scoring_team: int | None  # which team scores sequences/carres (0=NS, 1=EW, None=cancel)


def detect_belote(hand: tuple[Card, ...], trump: Suit) -> bool:
    """Check if hand contains both K and Q of trump."""
    king = Card(trump, Rank.KING)
    queen = Card(trump, Rank.QUEEN)
    return king in hand and queen in hand


@lru_cache(maxsize=128)
def detect_sequences(hand: tuple[Card, ...]) -> list[Sequence]:
    """Find all maximal sequences (tierce/quarte/quinte) in a hand.

    Sequences are based on rank order 7<8<9<10<J<Q<K<A within a single suit.
    Only sequences of length >= 3 count.

    Cached on the input hand tuple: detect_sequences is ~25% of `score_round`
    cost (measured 4.7.2), and the same `initial_hands` tuples flow through
    multiple call paths per round (`get_declarations` at bid-acceptance time
    in `game.py`, then again from `_detect_all_declarations` during scoring).
    Cards are frozen dataclasses, so tuple-of-card is hashable. The returned
    list is treated as read-only by every caller — `decls.extend(seqs)` and
    dict-storage are non-mutating. maxsize=128 covers ~32 full rounds before
    eviction (4 seats × 32).
    """
    # Group cards by suit
    by_suit: dict[Suit, list[int]] = {}
    for card in hand:
        if card.suit not in by_suit:
            by_suit[card.suit] = []
        by_suit[card.suit].append(_RANK_VALUES[card.rank])

    sequences: list[Sequence] = []
    # Optimization: Map (suit, rank_val) to card for fast lookup within the suit group
    card_map = {(c.suit, _RANK_VALUES[c.rank]): c for c in hand}

    for suit, ranks in by_suit.items():
        ranks.sort()
        # Find consecutive runs
        if not ranks:
            continue
        run_start = 0
        for i in range(1, len(ranks)):
            if ranks[i] != ranks[i - 1] + 1:
                run_len = i - run_start
                if run_len >= 3:
                    top = ranks[i - 1]
                    seq_cards = tuple(
                        card_map[(suit, r)] for r in range(ranks[run_start], ranks[i - 1] + 1)
                    )
                    sequences.append(
                        Sequence(
                            length=run_len,
                            top_rank=top,
                            suit=suit,
                            is_trump=False,  # will be updated later
                            cards=seq_cards,
                        )
                    )
                run_start = i
        # Final run
        run_len = len(ranks) - run_start
        if run_len >= 3:
            top = ranks[-1]
            seq_cards = tuple(card_map[(suit, r)] for r in range(ranks[run_start], ranks[-1] + 1))
            sequences.append(
                Sequence(
                    length=run_len,
                    top_rank=top,
                    suit=suit,
                    is_trump=False,
                    cards=seq_cards,
                )
            )
    return sequences


def detect_carres(hand: tuple[Card, ...]) -> list[Carre]:
    """Find all carrés (four of a kind by rank) in a hand."""
    by_rank: dict[Rank, list[Card]] = {}
    for card in hand:
        if card.rank not in by_rank:
            by_rank[card.rank] = []
        by_rank[card.rank].append(card)

    carres: list[Carre] = []
    for rank, cards in by_rank.items():
        if len(cards) == 4:
            carres.append(
                Carre(
                    rank=_RANK_VALUES[rank],
                    cards=tuple(cards),
                )
            )
    return carres


def _sequence_strength(seq: Sequence) -> tuple[int, int, bool]:
    """Comparable tuple for sequence priority: (length, top_rank, is_trump)."""
    return (seq.length, seq.top_rank, seq.is_trump)


def _carre_strength(carre: Carre) -> tuple[int, int]:
    """Comparable tuple for carré priority: (points, rank)."""
    return (_CARRE_POINTS.get(_VALUE_TO_RANK[carre.rank], 0), carre.rank)


def _best_sequence(sequences: list[Sequence]) -> Sequence | None:
    if not sequences:
        return None
    return max(sequences, key=_sequence_strength)


def _best_carre(carres: list[Carre]) -> Carre | None:
    if not carres:
        return None
    return max(carres, key=_carre_strength)


def _carre_points(carre: Carre) -> int:
    # 3.6.0 audit L3: use `.get(..., 0)` to match the sibling lookups at
    # the file's other carre / sequence sites. The dict is currently
    # complete so this is asymmetry-only — but it makes a future-Rank
    # addition fail-soft instead of crashing scoring mid-round.
    return _CARRE_POINTS.get(_VALUE_TO_RANK[carre.rank], 0)


def _sequence_points(seq: Sequence) -> int:
    return _SEQUENCE_POINTS.get(min(seq.length, 5), 0)


@dataclass(slots=True)
class _TeamDecls:
    """One team's declarations, each list paired with the declaring seats."""

    seqs: list[Sequence] = field(default_factory=list)
    seq_seats: list[Seat] = field(default_factory=list)
    carres: list[Carre] = field(default_factory=list)
    carre_seats: list[Seat] = field(default_factory=list)
    belote: bool = False


def _collect_team_decls(
    decls_per_seat: dict[Seat, SeatDeclarations], trump: Suit | None
) -> tuple[_TeamDecls, _TeamDecls]:
    """Pool per-seat declarations by team (NS, EW): sequences re-flagged for
    the trump suit, zero-point carrés dropped."""
    teams = (_TeamDecls(), _TeamDecls())
    for seat, decls in decls_per_seat.items():
        team = teams[team_of(seat)]
        seqs = [
            Sequence(
                length=s.length,
                top_rank=s.top_rank,
                suit=s.suit,
                is_trump=(s.suit == trump),
                cards=s.cards,
            )
            for s in decls["sequences"]
        ]
        carres = [c for c in decls["carres"] if _carre_points(c) > 0]
        team.seqs.extend(seqs)
        team.seq_seats.extend([seat] * len(seqs))
        team.carres.extend(carres)
        team.carre_seats.extend([seat] * len(carres))
        team.belote = team.belote or decls["belote"]
    return teams


def _higher(ns_key: tuple[int, ...], ew_key: tuple[int, ...]) -> int | None:
    """0 if NS's key is stronger, 1 if EW's, None on a tie."""
    if ns_key > ew_key:
        return 0
    if ew_key > ns_key:
        return 1
    return None


def _first_announcer(
    seat_order: tuple[Seat, ...],
    ns_hits: Iterable[tuple[Seat, bool]],
    ew_hits: Iterable[tuple[Seat, bool]],
) -> int | None:
    """Tie-break: the team of the first seat (announce order, clockwise from
    the taker) holding a tied declaration. No taker → None (legacy cancel).

    4.6.5: a per-seat team lookup walked once in seat order, O(seats)."""
    if not seat_order:
        return None
    seat_team: dict[Seat, int] = {}
    for seat, hit in ns_hits:
        if hit:
            seat_team.setdefault(seat, 0)
    for seat, hit in ew_hits:
        if hit:
            seat_team.setdefault(seat, 1)
    for seat in seat_order:
        if seat in seat_team:
            return seat_team[seat]
    return None


def resolve_declarations(
    decls_per_seat: dict[Seat, SeatDeclarations],
    trump: Suit | None,
    taker: Seat | None = None,
) -> ResolvedDeclarations:
    """Resolve declarations per §3.7.

    When two declarations have identical strength, standard Belote-Coinché
    awards the tie to the first announcer (the team whose seat declared first
    during the first trick — announcement order starts at the taker and goes
    clockwise). Pass `taker` to enable that rule; without it, ties fall back
    to the historical "cancel" behaviour.
    """
    ns, ew = _collect_team_decls(decls_per_seat, trump)
    ns_best_seq = _best_sequence(ns.seqs)
    ew_best_seq = _best_sequence(ew.seqs)
    ns_best_carre = _best_carre(ns.carres)
    ew_best_carre = _best_carre(ew.carres)

    seat_order: tuple[Seat, ...] = ()
    if taker is not None:
        s1 = taker.next_seat()
        s2 = s1.next_seat()
        seat_order = (taker, s1, s2, s2.next_seat())

    scoring_team: int | None = None
    # Carrés outrank any sequence.
    if ns_best_carre and ew_best_carre:
        # Higher carré points, then higher rank; a full tie → first announcer.
        scoring_team = _higher(
            (_carre_points(ns_best_carre), ns_best_carre.rank),
            (_carre_points(ew_best_carre), ew_best_carre.rank),
        )
        if scoring_team is None:
            tied_rank = ns_best_carre.rank
            scoring_team = _first_announcer(
                seat_order,
                (
                    (cs, c.rank == tied_rank)
                    for c, cs in zip(ns.carres, ns.carre_seats, strict=True)
                ),
                (
                    (cs, c.rank == tied_rank)
                    for c, cs in zip(ew.carres, ew.carre_seats, strict=True)
                ),
            )
    elif ns_best_carre:
        scoring_team = 0
    elif ew_best_carre:
        scoring_team = 1
    elif ns_best_seq and ew_best_seq:
        tied = _sequence_strength(ns_best_seq)
        scoring_team = _higher(tied, _sequence_strength(ew_best_seq))
        if scoring_team is None:
            scoring_team = _first_announcer(
                seat_order,
                (
                    (ss, _sequence_strength(q) == tied)
                    for q, ss in zip(ns.seqs, ns.seq_seats, strict=True)
                ),
                (
                    (ss, _sequence_strength(q) == tied)
                    for q, ss in zip(ew.seqs, ew.seq_seats, strict=True)
                ),
            )
    elif ns_best_seq:
        scoring_team = 0
    elif ew_best_seq:
        scoring_team = 1

    return ResolvedDeclarations(
        ns_sequences=tuple(ns.seqs),
        ew_sequences=tuple(ew.seqs),
        ns_carres=tuple(ns.carres),
        ew_carres=tuple(ew.carres),
        ns_belote=ns.belote,
        ew_belote=ew.belote,
        scoring_team=scoring_team,
    )


class SeatDeclarations(TypedDict):
    sequences: list[Sequence]
    carres: list[Carre]
    belote: bool


def _detect_all_declarations(state: GameState, trump: Suit | None) -> dict[Seat, SeatDeclarations]:
    """Internal helper to find all potential declarations in all hands.

    Sequences and carrés exist under every contract (Sans Atout included), so
    `trump=None` is acceptable here. Belote is disabled under Sans Atout and
    Tout Atout (no unique K+Q-of-trump) — `detect_belote` is skipped.
    """
    decls_per_seat: dict[Seat, SeatDeclarations] = {}
    no_belote_contract = trump is None or trump == Suit.TOUT_ATOUT
    for seat in Seat:
        # Default empty decls
        decls_per_seat[seat] = {
            "sequences": [],
            "carres": [],
            "belote": False,
        }

        # Use initial_hands if in scoring phase, else current hands (bidding phase)
        hand = (
            state.initial_hands[seat.value] if state.phase == Phase.SCORING else state.hand_of(seat)
        )
        if not hand:
            continue

        seqs = detect_sequences(hand)
        # 7/8 carrés are detected (detect_carres) but are not declarations:
        # a 0-point carré must not outrank the other team's sequences.
        carres = [c for c in detect_carres(hand) if _carre_points(c) > 0]
        has_belote = False if no_belote_contract else detect_belote(hand, trump)  # type: ignore[arg-type]
        decls_per_seat[seat] = {
            "sequences": seqs,
            "carres": carres,
            "belote": has_belote,
        }
    return decls_per_seat


def _decl_short_label(d: Declaration) -> str:
    if d.kind == "belote":
        return "Belote"
    if d.kind == "rebelote":
        return "Rebelote"
    if d.kind == "carre" and isinstance(d.detail, Carre):
        rank = _VALUE_TO_RANK.get(d.detail.rank)
        return f"Carré-{rank.value}" if rank else "Carré"
    if d.kind == "sequence" and isinstance(d.detail, Sequence):
        pts = _sequence_points(d.detail)
        return f"{pts}{d.detail.suit.symbol}"
    return d.kind


def get_declarations(state: GameState) -> tuple[Declaration, ...]:
    """Pre-calculate all declarations from initial hands.

    Sequences and carrés exist under every contract (Sans Atout included).
    Returns empty when the contract isn't established (no trump set and
    contract field unset) — pre-existing call sites that only set `trump`
    keep working.
    """
    if state.trump is None and state.contract != Contract.SANS_ATOUT:
        return ()

    decls_per_seat = _detect_all_declarations(state, state.trump)
    resolved = resolve_declarations(decls_per_seat, state.trump, state.taker)
    scoring_team = resolved.scoring_team

    all_decls: list[Declaration] = []

    # We only care about sequences and carres if they actually score
    if scoring_team is not None:
        for seat in Seat:
            if team_of(seat) == scoring_team:
                decls = decls_per_seat[seat]
                for seq in decls["sequences"]:
                    all_decls.append(Declaration(seat, "sequence", seq))
                for carre in decls["carres"]:
                    all_decls.append(Declaration(seat, "carre", carre))

    # Belote is separate from sequence scoring
    if resolved.ns_belote:
        for s in (Seat.SOUTH, Seat.NORTH):
            if decls_per_seat[s]["belote"]:
                all_decls.append(Declaration(s, "belote"))

    if resolved.ew_belote:
        for s in (Seat.EAST, Seat.WEST):
            if decls_per_seat[s]["belote"]:
                all_decls.append(Declaration(s, "belote"))

    return tuple(all_decls)
