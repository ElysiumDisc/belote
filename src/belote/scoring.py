from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from .config import GLOBAL_CONFIG
from .deck import Card, Contract, Rank, Suit
from .deck import card_points as card_points_fn
from .game import (
    Carre,
    Declaration,
    GameState,
    Phase,
    RoundScore,
    Seat,
    Sequence,
    TrickCard,
    compute_trick_winners,
    reset_round_fields,
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
class ScoringBreakdown:
    taker_team: int  # 0 = NS, 1 = EW
    # Points won at the table (including 10 de der)
    table_taker_pts: int
    table_defender_pts: int
    # Points actually credited to the score (after chute/litige logic)
    credit_taker_pts: int
    credit_defender_pts: int
    last_trick_team: int | None  # who got the +10
    taker_declarations: int
    defender_declarations: int
    taker_belote: int
    defender_belote: int
    taker_rebelote: bool
    defender_rebelote: bool
    taker_total: int  # card_pts + decls + belote + litige
    defender_total: int
    is_capot: bool
    is_failed: bool
    is_litige: bool = False
    litige_points_awarded: int = 0
    messages: tuple[str, ...] = ()
    # Per-team trick counts. Default 0 keeps existing call sites working;
    # `score_round` populates these from its pre-computed `winners` so
    # `apply_round_score` doesn't have to re-walk completed_tricks.
    tricks_ns: int = 0
    tricks_ew: int = 0


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


def detect_sequences(hand: tuple[Card, ...]) -> list[Sequence]:
    """Find all maximal sequences (tierce/quarte/quinte) in a hand.

    Sequences are based on rank order 7<8<9<10<J<Q<K<A within a single suit.
    Only sequences of length >= 3 count.
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
                        card_map[(suit, r)]
                        for r in range(ranks[run_start], ranks[i - 1] + 1)
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
            seq_cards = tuple(
                card_map[(suit, r)]
                for r in range(ranks[run_start], ranks[-1] + 1)
            )
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
    ns_seqs: list[Sequence] = []
    ew_seqs: list[Sequence] = []
    ns_carres: list[Carre] = []
    ew_carres: list[Carre] = []
    ns_carre_seats: list[Seat] = []  # parallel to ns_carres
    ew_carre_seats: list[Seat] = []
    ns_seq_seats: list[Seat] = []  # parallel to ns_seqs
    ew_seq_seats: list[Seat] = []
    ns_belote = False
    ew_belote = False

    for seat, decls in decls_per_seat.items():
        updated_seqs = [
            Sequence(
                length=s.length,
                top_rank=s.top_rank,
                suit=s.suit,
                is_trump=(s.suit == trump),
                cards=s.cards,
            )
            for s in decls["sequences"]
        ]
        carres = list(decls["carres"])
        has_belote = decls["belote"]

        if team_of(seat) == 0:
            ns_seqs.extend(updated_seqs)
            ns_carres.extend(carres)
            ns_seq_seats.extend([seat] * len(updated_seqs))
            ns_carre_seats.extend([seat] * len(carres))
            ns_belote = ns_belote or has_belote
        else:
            ew_seqs.extend(updated_seqs)
            ew_carres.extend(carres)
            ew_seq_seats.extend([seat] * len(updated_seqs))
            ew_carre_seats.extend([seat] * len(carres))
            ew_belote = ew_belote or has_belote

    # Determine which team scores sequences/carres
    ns_best_seq = _best_sequence(ns_seqs)
    ew_best_seq = _best_sequence(ew_seqs)
    ns_best_carre = _best_carre(ns_carres)
    ew_best_carre = _best_carre(ew_carres)

    # Announce-order walk: clockwise from taker. Used by both tie-break
    # resolvers below — compute once.
    seat_order: tuple[Seat, ...] = ()
    if taker is not None:
        s1 = taker.next_seat()
        s2 = s1.next_seat()
        s3 = s2.next_seat()
        seat_order = (taker, s1, s2, s3)

    def _resolve_tie_carre() -> int | None:
        # 4.6.5: pre-build a per-seat team lookup once, then walk seat_order
        # in O(seats). Pre-fix this was nested zips inside the seat loop —
        # O(seats × decls); both factors tiny in practice but the dict form
        # also reads more clearly than "first-match wins NS, else EW".
        if taker is None:
            return None  # legacy cancel behaviour
        assert ns_best_carre is not None and ew_best_carre is not None
        tied_rank = ns_best_carre.rank
        seat_team: dict[Seat, int] = {}
        for c, cs in zip(ns_carres, ns_carre_seats, strict=True):
            if c.rank == tied_rank:
                seat_team.setdefault(cs, 0)
        for c, cs in zip(ew_carres, ew_carre_seats, strict=True):
            if c.rank == tied_rank:
                seat_team.setdefault(cs, 1)
        for s in seat_order:
            if s in seat_team:
                return seat_team[s]
        return None

    def _resolve_tie_seq() -> int | None:
        # Symmetric to _resolve_tie_carre — see comment there for the
        # O(seats × decls) → O(seats) reasoning.
        if taker is None:
            return None
        assert ns_best_seq is not None and ew_best_seq is not None
        tied_strength = _sequence_strength(ns_best_seq)
        seat_team: dict[Seat, int] = {}
        for seq, ss in zip(ns_seqs, ns_seq_seats, strict=True):
            if _sequence_strength(seq) == tied_strength:
                seat_team.setdefault(ss, 0)
        for seq, ss in zip(ew_seqs, ew_seq_seats, strict=True):
            if _sequence_strength(seq) == tied_strength:
                seat_team.setdefault(ss, 1)
        for s in seat_order:
            if s in seat_team:
                return seat_team[s]
        return None

    scoring_team: int | None = None

    # Carrés outrank any sequence
    if ns_best_carre and ew_best_carre:
        # Both have carrés - higher carré wins
        ns_cp = _carre_points(ns_best_carre)
        ew_cp = _carre_points(ew_best_carre)
        if ns_cp > ew_cp:
            scoring_team = 0
        elif ew_cp > ns_cp:
            scoring_team = 1
        else:
            # Same carré strength - compare rank
            if ns_best_carre.rank > ew_best_carre.rank:
                scoring_team = 0
            elif ew_best_carre.rank > ns_best_carre.rank:
                scoring_team = 1
            else:
                scoring_team = _resolve_tie_carre()  # first-announcer or cancel
    elif ns_best_carre:
        scoring_team = 0
    elif ew_best_carre:
        scoring_team = 1
    elif ns_best_seq and ew_best_seq:
        ns_str = _sequence_strength(ns_best_seq)
        ew_str = _sequence_strength(ew_best_seq)
        if ns_str > ew_str:
            scoring_team = 0
        elif ew_str > ns_str:
            scoring_team = 1
        else:
            scoring_team = _resolve_tie_seq()  # first-announcer or cancel
    elif ns_best_seq:
        scoring_team = 0
    elif ew_best_seq:
        scoring_team = 1

    return ResolvedDeclarations(
        ns_sequences=tuple(ns_seqs),
        ew_sequences=tuple(ew_seqs),
        ns_carres=tuple(ns_carres),
        ew_carres=tuple(ew_carres),
        ns_belote=ns_belote,
        ew_belote=ew_belote,
        scoring_team=scoring_team,
    )


def is_capot(
    state: GameState,
    tricks: list[tuple[TrickCard, ...]] | None = None,
    winners: list[Seat | None] | None = None,
) -> int | None:
    """Check if either team won all 8 tricks. Returns team index (0=NS, 1=EW) or None.

    Honors La Rupture (`no_consecutive_team_wins`) for both the default
    (`state.completed_tricks`) and explicit-tricks branches. Capot under La
    Rupture is effectively impossible; the live HUD CAPOT announcement on the
    8th trick (`gameflow.py` passes `tricks=completed + [current]`) must use
    the same Rupture-aware resolution as the final scoring path or it will
    falsely announce CAPOT mid-round.

    `winners` is honored only when `tricks is None` — when a caller already
    resolved winners for `state.completed_tricks`, pass them in to avoid the
    repeated trick-winner walk that `score_round` would otherwise trigger.
    """
    is_sa = state.contract == Contract.SANS_ATOUT
    if tricks is None:
        if winners is None:
            winners = compute_trick_winners(state, state.trump, is_sa)
    else:
        if not tricks or len(tricks) < 8:
            return None
        winners = compute_trick_winners(state, state.trump, is_sa, tuple(tricks))

    if not winners or len(winners) < 8:
        return None
    first_winner = winners[0]
    if first_winner is None:
        return None
    winning_team = team_of(first_winner)

    for w in winners[1:]:
        if w is None or team_of(w) != winning_team:
            return None
    return winning_team


class SeatDeclarations(TypedDict):
    sequences: list[Sequence]
    carres: list[Carre]
    belote: bool


def _detect_all_declarations(
    state: GameState, trump: Suit | None
) -> dict[Seat, SeatDeclarations]:
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
        carres = detect_carres(hand)
        has_belote = False if no_belote_contract else detect_belote(hand, trump)  # type: ignore[arg-type]
        decls_per_seat[seat] = {
            "sequences": seqs,
            "carres": carres,
            "belote": has_belote,
        }
    return decls_per_seat


# ── Zero-rank / ban-clubs helpers (3.6.0 audit M1+M2) ───────────────────────
# Single source of truth for boss zero-rank flags. Three sites used to inline
# this with subtle drift risk: every new zero-rank flag had to be added in
# three places or the HUD running total would silently disagree with the
# final round score. Use these helpers from every scoring path.


def _trick_zeroed_by_ban_clubs(
    trick: tuple[TrickCard, ...], bm: object
) -> bool:
    """``ban_clubs`` zeros the entire trick if ANY card is a club. Matches
    the rule in `_calculate_base_points` — earlier the separate-scoring
    branch checked only the lead card and silently awarded points for
    off-lead clubs."""
    return bool(getattr(bm, "ban_clubs", False)) and any(
        tc.card.suit == Suit.CLUBS for tc in trick
    )


def _card_points_with_zero_ranks(card: Card, trump: Suit | None, bm: object) -> int:
    """Per-card point value after applying every active zero-rank boss flag.

    When a new zero-rank flag is added to BossModifiers, this is the only
    site that needs to learn about it. Also propagates `seven_eight_trump`
    to `card_points` for correctness even though current point tables zero
    those cards anyway."""
    r = card.rank
    if getattr(bm, "kings_zero", False) and r == Rank.KING:
        return 0
    if getattr(bm, "tens_zero", False) and r == Rank.TEN:
        return 0
    if getattr(bm, "aces_zero", False) and r == Rank.ACE:
        return 0
    if getattr(bm, "jacks_zero", False) and r == Rank.JACK:
        return 0
    if getattr(bm, "ban_clubs", False) and card.suit == Suit.CLUBS:
        return 0
    return card_points_fn(card, trump, getattr(bm, "seven_eight_trump", False))


def card_points_with_modifiers(card: Card, trump: Suit | None, bm: object) -> int:
    """Public helper: per-card point value with active zero-rank boss flags.

    Mirrors `trick_card_points` (per-trick canonical helper) at the per-card
    level. Bidding heuristics (`ai.py`) call this to honor zero-rank bosses
    when evaluating Tout Atout / Sans Atout / regular-suit bid strength —
    pre-3.9.3 the AI used raw `card_points` and overbid on rank-suppressed
    hands.
    """
    return _card_points_with_zero_ranks(card, trump, bm)


def _trick_points_with_modifiers(
    trick: tuple[TrickCard, ...], trump: Suit | None, bm: object
) -> int:
    """Total card points for a single trick after every boss modifier."""
    if not trick:
        return 0
    if _trick_zeroed_by_ban_clubs(trick, bm):
        return 0
    return sum(_card_points_with_zero_ranks(tc.card, trump, bm) for tc in trick)


def trick_card_points(state: GameState, trick: tuple[TrickCard, ...]) -> int:
    """Card-point sum for a single trick, applying boss zero-rank flags and
    `ban_clubs`. Public helper so non-scoring callers (gameflow/a11y, HUD)
    don't duplicate the flag table.

    Returns 0 if the trick is empty. The dix-de-der bonus is NOT included
    here — it's a per-round concept, not per-trick.
    """
    return _trick_points_with_modifiers(trick, state.trump, state.boss_modifiers)


def _calculate_base_points(
    state: GameState,
    trump: Suit | None,
    winners: list[Seat | None] | None = None,
) -> tuple[int, int]:
    """Calculate raw card points per team, considering boss modifiers.

    `trump=None` is the Sans Atout case. `card_points(c, None)` already returns
    the SA non-trump scale, so the inner arithmetic is unchanged.

    `winners`, when provided, must be aligned with ``state.completed_tricks``;
    pre-computing it once in ``score_round`` avoids redoing the trick-winner
    computation in the sibling helpers.
    """
    taker_team = team_of(state.taker) if state.taker is not None else 0
    taker_pts = 0
    defender_pts = 0
    is_sa = state.contract == Contract.SANS_ATOUT
    bm = state.boss_modifiers

    if winners is None:
        winners = compute_trick_winners(state, trump, is_sa)

    for trick, winner in zip(state.completed_tricks, winners, strict=True):
        if winner is None:
            continue
        trick_pts = _trick_points_with_modifiers(trick, trump, bm)
        if team_of(winner) == taker_team:
            taker_pts += trick_pts
        else:
            defender_pts += trick_pts

    return taker_pts, defender_pts


def _apply_scoring_modifiers(
    state: GameState,
    taker_pts: int,
    defender_pts: int,
    winners: list[Seat | None] | None = None,
) -> tuple[int, int, list[str]]:
    """Apply complex boss scoring modifiers (Compétition, Reine Noire).

    ``winners`` may be supplied by the caller to avoid re-running
    ``trick_winner_seat`` for every completed trick — both modifier branches
    iterate the same trick list as ``_calculate_base_points``.
    """
    messages: list[str] = []
    trump = state.trump
    is_sa = state.contract == Contract.SANS_ATOUT
    taker_team = team_of(state.taker) if state.taker is not None else 0

    if winners is None:
        winners = compute_trick_winners(state, trump, is_sa)

    # Boss: La Competition (Separate scoring) — applies under any active
    # contract, including Sans Atout (trump=None).
    if state.boss_modifiers.separate_scoring and state.contract is not None:
        scores = {Seat.SOUTH: 0, Seat.NORTH: 0, Seat.EAST: 0, Seat.WEST: 0}
        bm = state.boss_modifiers
        for trick, winner in zip(state.completed_tricks, winners, strict=True):
            if winner is None:
                continue
            scores[winner] += _trick_points_with_modifiers(trick, trump, bm)

        # Add 10 de der to individual winner (suppressed by Le Zéro Final).
        if (
            state.last_trick_winner in scores
            and not state.boss_modifiers.no_dix_de_der
        ):
            scores[state.last_trick_winner] += 10

        if taker_team == 0:
            taker_pts = max(scores[Seat.SOUTH], scores[Seat.NORTH])
            defender_pts = max(scores[Seat.EAST], scores[Seat.WEST])
        else:
            taker_pts = max(scores[Seat.EAST], scores[Seat.WEST])
            defender_pts = max(scores[Seat.SOUTH], scores[Seat.NORTH])
        messages.append("Compétition: Higher individual score used!")

    # Boss: La Reine Noire (Queen of Spades penalty)
    if state.boss_modifiers.queen_spades_penalty:
        qs = Card(Suit.SPADES, Rank.QUEEN)
        for trick, winner in zip(state.completed_tricks, winners, strict=True):
            if winner is not None and any(tc.card == qs for tc in trick):
                if team_of(winner) == taker_team:
                    taker_pts -= 25
                else:
                    defender_pts -= 25
        messages.append("Reine Noire: -25 points for capture!")

    return taker_pts, defender_pts, messages


@dataclass(frozen=True, slots=True)
class _ScoringContext:
    """3.7.1 (D1): bundle of pre-computed values used across score_round helpers.

    Built once at the top of `score_round`; threaded into the per-section
    helpers so they don't each re-derive the same 4-5 fields off GameState.
    Internal — no public consumers.
    """
    state: GameState
    trump: Suit | None
    taker: Seat
    taker_team: int
    defender_team: int
    is_sa: bool
    winners: list[Seat | None]
    tricks_ns: int
    tricks_ew: int


def _empty_breakdown() -> ScoringBreakdown:
    """Return the no-op breakdown for rounds without an active contract."""
    return ScoringBreakdown(
        taker_team=team_of(Seat.SOUTH),
        table_taker_pts=0,
        table_defender_pts=0,
        credit_taker_pts=0,
        credit_defender_pts=0,
        last_trick_team=None,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=0,
        defender_total=0,
        is_capot=False,
        is_failed=False,
        messages=(),
    )


def _compute_belote_points(ctx: _ScoringContext) -> tuple[int, int, bool, bool]:
    """Resolve belote/rebelote points for taker vs defender.

    Returns (taker_belote, defender_belote, taker_rebelote, defender_rebelote).
    """
    state = ctx.state
    # Prefer the captured announcer seat (recorded at the moment belote was
    # declared) over re-deriving from belote_holders — under L'Anarchie the
    # current state.trump differs from the trump at announcement time, and
    # the dict lookup would miss the announcer entirely.
    if state.belote_announcer is not None:
        belote_holder: Seat | None = state.belote_announcer
    else:
        belote_holder = state.belote_holders.get(ctx.trump) if ctx.trump is not None else None

    no_belote = state.boss_modifiers.no_belote or bool(
        state._joker_state.get("no_belote_rebelote")
    )
    if belote_holder is None or no_belote:
        return 0, 0, False, False

    holder_team = team_of(belote_holder)
    points = 0
    is_rebelote = state.belote_tracker[1]
    if is_rebelote:
        points = GLOBAL_CONFIG.REBELOTE_POINTS
    elif state.belote_tracker[0]:
        points = GLOBAL_CONFIG.BELOTE_POINTS

    if holder_team == ctx.taker_team:
        return points, 0, is_rebelote, False
    return 0, points, False, is_rebelote


def _compute_declaration_points(
    ctx: _ScoringContext, resolved: ResolvedDeclarations
) -> tuple[int, int]:
    """Sum taker/defender declaration points, applying announce_x2 and declarations_zero."""
    state = ctx.state
    scoring_team = resolved.scoring_team
    taker_declarations = 0
    defender_declarations = 0

    if scoring_team is not None:
        if scoring_team == ctx.taker_team:
            seqs = resolved.ns_sequences if ctx.taker_team == 0 else resolved.ew_sequences
            carres = resolved.ns_carres if ctx.taker_team == 0 else resolved.ew_carres
            for seq in seqs:
                taker_declarations += _sequence_points(seq)
            for carre in carres:
                taker_declarations += _carre_points(carre)
        else:
            seqs = resolved.ns_sequences if ctx.defender_team == 0 else resolved.ew_sequences
            carres = resolved.ns_carres if ctx.defender_team == 0 else resolved.ew_carres
            for seq in seqs:
                defender_declarations += _sequence_points(seq)
            for carre in carres:
                defender_declarations += _carre_points(carre)

    # Le Marseillais deck: annonces (Tierce/Quarte/Quinte/Carré) score x2.
    if state._joker_state.get("announce_x2"):
        taker_declarations *= 2
        defender_declarations *= 2

    # 3.0.0 Le Mime boss: all declaration points zeroed for the round.
    if state.boss_modifiers.declarations_zero:
        return 0, 0
    return taker_declarations, defender_declarations


def _score_capot_outcome(
    ctx: _ScoringContext,
    capot_winner_team: int,
    taker_card_pts: int,
    defender_card_pts: int,
    taker_declarations: int,
    defender_declarations: int,
    taker_belote: int,
    defender_belote: int,
    taker_rebelote: bool,
    defender_rebelote: bool,
    last_trick_team: int | None,
    messages: list[str],
) -> ScoringBreakdown:
    """Finalise a capot round (taker or defender capot, contract-aware base)."""
    state = ctx.state
    messages.append("Capot!")
    # Capot base scales by contract: SA → 220, TA → 348, normal → 252.
    if state.contract == Contract.SANS_ATOUT:
        capot_base = GLOBAL_CONFIG.CAPOT_BASE_SANS_ATOUT
    elif state.contract == Contract.TOUT_ATOUT:
        capot_base = GLOBAL_CONFIG.CAPOT_BASE_TOUT_ATOUT
    else:
        capot_base = GLOBAL_CONFIG.CAPOT_BASE

    # Le Zéro Final: if last-trick bonus is suppressed, the Capot reward (which
    # includes the +10) must drop by 10 too. Matches the chute-pool logic
    # in _score_normal_outcome.
    if state.boss_modifiers.no_dix_de_der:
        capot_base -= GLOBAL_CONFIG.LAST_TRICK_BONUS

    is_failed = False
    if capot_winner_team == ctx.taker_team:
        taker_total = (
            capot_base
            + taker_declarations
            + defender_declarations
            + taker_belote
            + state.litige_points
        )
        defender_total = defender_belote
    else:
        is_failed = True
        defender_total = (
            capot_base
            + defender_declarations
            + taker_declarations
            + defender_belote
            + state.litige_points
        )
        taker_total = taker_belote

    return ScoringBreakdown(
        taker_team=ctx.taker_team,
        table_taker_pts=taker_card_pts,
        table_defender_pts=defender_card_pts,
        credit_taker_pts=taker_card_pts if not is_failed else 0,
        credit_defender_pts=defender_card_pts if is_failed else 0,
        last_trick_team=last_trick_team,
        taker_declarations=taker_declarations,
        defender_declarations=defender_declarations,
        taker_belote=taker_belote,
        defender_belote=defender_belote,
        taker_rebelote=taker_rebelote,
        defender_rebelote=defender_rebelote,
        taker_total=taker_total,
        defender_total=defender_total,
        is_capot=True,
        is_failed=is_failed,
        messages=tuple(messages),
        tricks_ns=ctx.tricks_ns,
        tricks_ew=ctx.tricks_ew,
    )


def _score_normal_outcome(
    ctx: _ScoringContext,
    taker_card_pts: int,
    defender_card_pts: int,
    taker_declarations: int,
    defender_declarations: int,
    taker_belote: int,
    defender_belote: int,
    taker_rebelote: bool,
    defender_rebelote: bool,
    last_trick_team: int | None,
    messages: list[str],
) -> ScoringBreakdown:
    """Finalise a non-capot round: litige / chute / fulfilled + Malédiction."""
    state = ctx.state
    comp_taker = taker_card_pts + taker_declarations
    comp_defender = defender_card_pts + defender_declarations

    is_failed = False
    is_litige = False
    litige_points_awarded = 0
    taker_total = 0
    defender_total = 0

    if comp_taker == comp_defender:
        # La Balance voucher: taker wins automatically on a card-point tie.
        if state._joker_state.get("tie_breaks_for_taker"):
            messages.append("La Balance: tie awarded to taker.")
            taker_total = (
                taker_card_pts + taker_declarations + taker_belote + state.litige_points
            )
            defender_total = defender_card_pts + defender_declarations + defender_belote
        else:
            is_litige = True
            messages.append("Litige! (tie)")
            defender_total = defender_card_pts + defender_declarations + defender_belote
            taker_total = taker_belote
            litige_points_awarded = taker_card_pts + taker_declarations
    elif comp_taker < comp_defender:
        is_failed = True
        messages.append("Chute! (bid failed)")
        # Contract-aware total for the chute formula. SA/TA score over a
        # different deck total — the defender pockets the full hand.
        if state.contract == Contract.SANS_ATOUT:
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS_SANS_ATOUT
        elif state.contract == Contract.TOUT_ATOUT:
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS_TOUT_ATOUT
        else:
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS
        # Le Zéro Final boss zeros the dix-de-der; the chute pool must drop
        # the +10 too. The in-round scoring path already gates the bonus on
        # no_dix_de_der; this branch used to ignore it.
        dix_de_der = 0 if state.boss_modifiers.no_dix_de_der else GLOBAL_CONFIG.LAST_TRICK_BONUS
        defender_total = (
            chute_total
            + dix_de_der
            + defender_declarations
            + taker_declarations
            + defender_belote
            + state.litige_points
        )
        taker_total = taker_belote
    else:
        messages.append("Contract fulfilled!")
        taker_total = taker_card_pts + taker_declarations + taker_belote + state.litige_points
        defender_total = defender_card_pts + defender_declarations + defender_belote

    # Boss: La Malediction (Invert scoring)
    if state.boss_modifiers.invert_scoring:
        t_tricks = ctx.tricks_ns if ctx.taker_team == 0 else ctx.tricks_ew
        defender_tricks = 8 - t_tricks
        if t_tricks > defender_tricks:
            taker_total = 0
            messages.append("Malédiction: Taker won more tricks!")
        elif defender_tricks > t_tricks:
            defender_total = 0
            messages.append("Malédiction: Defense won more tricks!")

    return ScoringBreakdown(
        taker_team=ctx.taker_team,
        table_taker_pts=taker_card_pts,
        table_defender_pts=defender_card_pts,
        credit_taker_pts=taker_card_pts if not (is_failed or is_litige) else 0,
        credit_defender_pts=defender_card_pts,
        last_trick_team=last_trick_team,
        taker_declarations=taker_declarations,
        defender_declarations=defender_declarations,
        taker_belote=taker_belote,
        defender_belote=defender_belote,
        taker_rebelote=taker_rebelote,
        defender_rebelote=defender_rebelote,
        taker_total=taker_total,
        defender_total=defender_total,
        is_capot=False,
        is_failed=is_failed,
        is_litige=is_litige,
        litige_points_awarded=litige_points_awarded,
        messages=tuple(messages),
        tricks_ns=ctx.tricks_ns,
        tricks_ew=ctx.tricks_ew,
    )


def score_round(state: GameState) -> ScoringBreakdown:
    """Score the completed round per official rules.

    3.7.1 (D1): orchestrator over `_compute_belote_points`,
    `_compute_declaration_points`, `_score_capot_outcome`, and
    `_score_normal_outcome`. Behaviour unchanged from 3.6.0; public signature
    and `ScoringBreakdown` shape are the contract.
    """
    # An active contract has either a trump suit set or contract=="sans_atout"
    # (the only legal case where trump is None mid-game). Pre-existing tests
    # build states with `trump=Suit.X` and `contract=None` — those still score
    # via the trump check.
    contract_active = state.trump is not None or state.contract == Contract.SANS_ATOUT
    if not contract_active or state.taker is None:
        return _empty_breakdown()

    # Pre-compute the winner of each completed trick once. Base-points, the
    # boss modifier helpers, the Malédiction branch, and apply_round_score
    # all iterate the same list — without this the 8-trick walk runs 4× per
    # round. Per-team trick counts are derived once here too.
    trump = state.trump
    taker_team = team_of(state.taker)
    is_sa = state.contract == Contract.SANS_ATOUT
    winners: list[Seat | None] = compute_trick_winners(state, trump, is_sa)
    tricks_ns = sum(1 for w in winners if w is not None and team_of(w) == 0)
    tricks_ew = sum(1 for w in winners if w is not None and team_of(w) == 1)

    ctx = _ScoringContext(
        state=state,
        trump=trump,
        taker=state.taker,
        taker_team=taker_team,
        defender_team=1 - taker_team,
        is_sa=is_sa,
        winners=winners,
        tricks_ns=tricks_ns,
        tricks_ew=tricks_ew,
    )

    # 1. Base card points.
    taker_card_pts, defender_card_pts = _calculate_base_points(state, trump, winners)

    # 2. Last trick bonus (dix-de-der), gated by Le Zéro Final.
    last_trick_winner = state.last_trick_winner
    last_trick_team: int | None = None
    if last_trick_winner is not None and not state.boss_modifiers.no_dix_de_der:
        last_trick_team = team_of(last_trick_winner)
        if last_trick_team == taker_team:
            taker_card_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS
        else:
            defender_card_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS

    # 3. Complex boss scoring modifiers (Compétition, Reine Noire).
    taker_card_pts, defender_card_pts, messages = _apply_scoring_modifiers(
        state, taker_card_pts, defender_card_pts, winners
    )

    # 4. Resolve declarations from stored initial hands.
    decls_per_seat = _detect_all_declarations(state, trump)
    resolved = resolve_declarations(decls_per_seat, trump, state.taker)

    # 5. Belote / rebelote points.
    taker_belote, defender_belote, taker_rebelote, defender_rebelote = _compute_belote_points(ctx)

    # SA invariant: belote/rebelote requires a unique trump suit (K+Q of trump).
    # Under Sans Atout there is no trump, so neither side can ever have earned
    # belote points. Pin once at contract level (covers capot AND non-capot).
    if state.contract == Contract.SANS_ATOUT:
        assert taker_belote == 0 and defender_belote == 0, (
            f"Sans Atout cannot have belote points "
            f"(taker={taker_belote}, defender={defender_belote})"
        )

    # 6. Declaration points (announce_x2 + declarations_zero applied inside).
    taker_declarations, defender_declarations = _compute_declaration_points(ctx, resolved)

    # 7. Capot check → branch to capot or normal outcome.
    capot_winner_team = is_capot(state, winners=winners)
    if capot_winner_team is not None:
        return _score_capot_outcome(
            ctx,
            capot_winner_team,
            taker_card_pts,
            defender_card_pts,
            taker_declarations,
            defender_declarations,
            taker_belote,
            defender_belote,
            taker_rebelote,
            defender_rebelote,
            last_trick_team,
            messages,
        )

    return _score_normal_outcome(
        ctx,
        taker_card_pts,
        defender_card_pts,
        taker_declarations,
        defender_declarations,
        taker_belote,
        defender_belote,
        taker_rebelote,
        defender_rebelote,
        last_trick_team,
        messages,
    )


def _decl_short_label(d: Declaration) -> str:
    if d.kind == "belote":
        return "Belote"
    if d.kind == "rebelote":
        return "Rebelote"
    if d.kind == "carre" and isinstance(d.detail, Carre):
        rank = _VALUE_TO_RANK.get(d.detail.rank)
        return f"Carré-{rank.value}" if rank else "Carré"
    if d.kind == "sequence" and isinstance(d.detail, Sequence):
        pts = _SEQUENCE_POINTS.get(d.detail.length, 0)
        return f"{pts}{d.detail.suit.symbol}"
    return d.kind


def apply_round_score(state: GameState, breakdown: ScoringBreakdown) -> GameState:
    """Apply round scoring result to team scores and advance state."""
    ns, ew = state.team_scores
    if breakdown.taker_team == 0:
        ns += breakdown.taker_total
        ew += breakdown.defender_total
    else:
        ew += breakdown.taker_total
        ns += breakdown.defender_total

    new_scores = (ns, ew)

    # Trick counts per team across the played round. score_round populates
    # these on the breakdown (3.1.0). When the breakdown was hand-constructed
    # (tests, replay tooling) and trick counts weren't passed, fall back to
    # the legacy walk so callers don't have to plumb winners themselves.
    tricks_ns = breakdown.tricks_ns
    tricks_ew = breakdown.tricks_ew
    if tricks_ns == 0 and tricks_ew == 0 and state.completed_tricks:
        is_sa = state.contract == Contract.SANS_ATOUT
        for w in compute_trick_winners(state, state.trump, is_sa):
            if w is None:
                continue
            if team_of(w) == 0:
                tricks_ns += 1
            else:
                tricks_ew += 1

    # Declaration summaries — only show the team(s) that actually scored decls,
    # which matches Belote's "best team takes all decls" rule.
    ns_decl_total = breakdown.taker_declarations if breakdown.taker_team == 0 else breakdown.defender_declarations
    ew_decl_total = breakdown.defender_declarations if breakdown.taker_team == 0 else breakdown.taker_declarations
    ns_decls = tuple(
        _decl_short_label(d) for d in state.declarations if team_of(d.seat) == 0
    ) if ns_decl_total > 0 else ()
    ew_decls = tuple(
        _decl_short_label(d) for d in state.declarations if team_of(d.seat) == 1
    ) if ew_decl_total > 0 else ()

    # Create RoundScore for history. Inlined kwargs (rather than splatting a
    # dict) so mypy can validate each field's type per-call.
    if breakdown.taker_team == 0:
        round_score = RoundScore(
            taker_team=0,
            ns_card_pts=breakdown.credit_taker_pts,
            ew_card_pts=breakdown.credit_defender_pts,
            ns_decl_pts=breakdown.taker_declarations,
            ew_decl_pts=breakdown.defender_declarations,
            ns_belote_pts=breakdown.taker_belote,
            ew_belote_pts=breakdown.defender_belote,
            ns_rebelote=breakdown.taker_rebelote,
            ew_rebelote=breakdown.defender_rebelote,
            ns_total=breakdown.taker_total,
            ew_total=breakdown.defender_total,
            is_failed=breakdown.is_failed,
            is_capot=breakdown.is_capot,
            is_litige=breakdown.is_litige,
            litige_points=breakdown.litige_points_awarded,
            contract=state.contract,
            trump=state.trump,
            taker_seat=state.taker,
            tricks_ns=tricks_ns,
            tricks_ew=tricks_ew,
            last_trick_winner=state.last_trick_winner,
            decl_summary_ns=ns_decls,
            decl_summary_ew=ew_decls,
        )
    else:
        round_score = RoundScore(
            taker_team=1,
            ns_card_pts=breakdown.credit_defender_pts,
            ew_card_pts=breakdown.credit_taker_pts,
            ns_decl_pts=breakdown.defender_declarations,
            ew_decl_pts=breakdown.taker_declarations,
            ns_belote_pts=breakdown.defender_belote,
            ew_belote_pts=breakdown.taker_belote,
            ns_rebelote=breakdown.defender_rebelote,
            ew_rebelote=breakdown.taker_rebelote,
            ns_total=breakdown.defender_total,
            ew_total=breakdown.taker_total,
            is_failed=breakdown.is_failed,
            is_capot=breakdown.is_capot,
            is_litige=breakdown.is_litige,
            litige_points=breakdown.litige_points_awarded,
            contract=state.contract,
            trump=state.trump,
            taker_seat=state.taker,
            tricks_ns=tricks_ns,
            tricks_ew=tricks_ew,
            last_trick_winner=state.last_trick_winner,
            decl_summary_ns=ns_decls,
            decl_summary_ew=ew_decls,
        )

    new_history = state.score_history + (round_score,)

    # Determine if game is over
    # Rule: If tie-breaker needed (ns == ew and both >= target), continue playing.
    if ns >= state.target or ew >= state.target:
        phase = Phase.DEAL if ns == ew else Phase.GAME_OVER
    else:
        phase = Phase.DEAL

    # Update litige pool: if it was a litige, add to it; otherwise reset it.
    new_litige_pool = 0
    if breakdown.is_litige:
        new_litige_pool = state.litige_points + breakdown.litige_points_awarded

    # Rotate dealer
    return reset_round_fields(
        state,
        team_scores=new_scores,
        dealer=state.dealer.next_seat(),
        phase=phase,
        score_history=new_history,
        litige_points=new_litige_pool,
    )


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
