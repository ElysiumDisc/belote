from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .deck import Card, Rank, Suit, card_points as card_points_fn
from .game import (
    GameState,
    Seat,
    Sequence,
    Carre,
    BeloteDecl,
    Declaration,
    RoundScore,
    team_of,
    partner,
    trick_winner_seat,
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

BELOTE_POINTS: Final = 20
LAST_TRICK_BONUS: Final = 10
CAPOT_BASE: Final = 250
TOTAL_POINTS: Final = 162  # 152 card points + 10 last trick


@dataclass(frozen=True, slots=True)
class ScoringBreakdown:
    taker_team: int  # 0 = NS, 1 = EW
    taker_card_pts: int
    defender_card_pts: int
    raw_taker_card_pts: int  # raw card points before failed-bid adjustment
    raw_defender_card_pts: int  # raw card points before failed-bid adjustment
    last_trick_team: int | None  # who got the +10
    taker_declarations: int
    defender_declarations: int
    taker_belote: int
    defender_belote: int
    taker_total: int
    defender_total: int
    is_capot: bool
    is_failed: bool
    messages: tuple[str, ...]


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
                        c for c in hand
                        if c.suit == suit and _RANK_VALUES[c.rank] >= ranks[run_start]
                        and _RANK_VALUES[c.rank] <= ranks[i - 1]
                    )
                    sequences.append(Sequence(
                        length=run_len,
                        top_rank=top,
                        suit=suit,
                        is_trump=False,  # will be updated later
                        cards=seq_cards,
                    ))
                run_start = i
        # Final run
        run_len = len(ranks) - run_start
        if run_len >= 3:
            top = ranks[-1]
            seq_cards = tuple(
                c for c in hand
                if c.suit == suit and _RANK_VALUES[c.rank] >= ranks[run_start]
                and _RANK_VALUES[c.rank] <= ranks[-1]
            )
            sequences.append(Sequence(
                length=run_len,
                top_rank=top,
                suit=suit,
                is_trump=False,
                cards=seq_cards,
            ))
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
            carres.append(Carre(
                rank=_RANK_VALUES[rank],
                cards=tuple(cards),
            ))
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
    return _CARRE_POINTS[_VALUE_TO_RANK[carre.rank]]


def _sequence_points(seq: Sequence) -> int:
    return _SEQUENCE_POINTS.get(seq.length, 0)


def resolve_declarations(
    decls_per_seat: dict[Seat, dict[str, object]],
    trump: Suit,
) -> ResolvedDeclarations:
    """Resolve declarations per §3.7.
    
    decls_per_seat maps each seat to a dict with keys:
      'sequences': list[Sequence]
      'carres': list[Carre]
      'belote': bool
    """
    ns_seqs: list[Sequence] = []
    ew_seqs: list[Sequence] = []
    ns_carres: list[Carre] = []
    ew_carres: list[Carre] = []
    ns_belote = False
    ew_belote = False

    for seat, decls in decls_per_seat.items():
        seqs = [s for s in decls.get("sequences", [])]
        updated_seqs = []
        for s in seqs:
            updated_seqs.append(Sequence(
                length=s.length, top_rank=s.top_rank, suit=s.suit,
                is_trump=(s.suit == trump), cards=s.cards,
            ))
        carres = list(decls.get("carres", []))
        has_belote = decls.get("belote", False)

        if team_of(seat) == 0:
            ns_seqs.extend(updated_seqs)
            ns_carres.extend(carres)
            ns_belote = ns_belote or has_belote
        else:
            ew_seqs.extend(updated_seqs)
            ew_carres.extend(carres)
            ew_belote = ew_belote or has_belote

    # Determine which team scores sequences/carres
    ns_best_seq = _best_sequence(ns_seqs)
    ew_best_seq = _best_sequence(ew_seqs)
    ns_best_carre = _best_carre(ns_carres)
    ew_best_carre = _best_carre(ew_carres)

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
                scoring_team = None  # cancel
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
            scoring_team = None  # cancel
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


def score_round(state: GameState) -> ScoringBreakdown:
    """Score the completed round per §3.8."""
    if state.trump is None or state.taker is None:
        return ScoringBreakdown(
            taker_team=team_of(Seat.SOUTH),
            taker_card_pts=0, defender_card_pts=0,
            raw_taker_card_pts=0, raw_defender_card_pts=0,
            last_trick_team=None,
            taker_declarations=0, defender_declarations=0,
            taker_belote=0, defender_belote=0,
            taker_total=0, defender_total=0,
            is_capot=False, is_failed=False,
            messages=(),
        )

    trump = state.trump
    taker_team = team_of(state.taker)
    defender_team = 1 - taker_team

    # Calculate card points per team from completed tricks
    taker_card_pts = 0
    defender_card_pts = 0
    for trick in state.completed_tricks:
        winner = trick_winner_seat(trick, trump)
        if winner is None:
            continue
        trick_pts = sum(card_points_fn(tc.card, trump) for tc in trick)
        if team_of(winner) == taker_team:
            taker_card_pts += trick_pts
        else:
            defender_card_pts += trick_pts

    # Last trick bonus
    last_trick_winner = state.last_trick_winner
    last_trick_team: int | None = None
    if last_trick_winner is not None:
        last_trick_team = team_of(last_trick_winner)
        if last_trick_team == taker_team:
            taker_card_pts += LAST_TRICK_BONUS
        else:
            defender_card_pts += LAST_TRICK_BONUS

    # --- Detect declarations from stored initial hands ---
    # Detect sequences, carres, and belote for each seat
    decls_per_seat: dict[Seat, dict[str, object]] = {}
    for seat in Seat:
        hand = state.hand_of(seat) if not state.completed_tricks else state.initial_hands[seat.value]
        seqs = detect_sequences(hand)
        carres = detect_carres(hand)
        has_belote = detect_belote(hand, trump)
        decls_per_seat[seat] = {
            "sequences": seqs,
            "carres": carres,
            "belote": has_belote,
        }

    resolved = resolve_declarations(decls_per_seat, trump)

    # Compute belote points per team
    taker_has_belote = any(
        decls_per_seat[s].get("belote", False)
        for s in Seat if team_of(s) == taker_team
    )
    defender_has_belote = any(
        decls_per_seat[s].get("belote", False)
        for s in Seat if team_of(s) == defender_team
    )
    taker_belote = BELOTE_POINTS if taker_has_belote else 0
    defender_belote = BELOTE_POINTS if defender_has_belote else 0

    # Compute declaration points (sequences + carres) per team
    scoring_team = resolved.scoring_team
    taker_declarations = 0
    defender_declarations = 0

    if scoring_team is not None:
        # Only the winning team scores their sequences and carres
        if scoring_team == taker_team:
            for seq in resolved.ns_sequences if taker_team == 0 else resolved.ew_sequences:
                taker_declarations += _sequence_points(seq)
            for carre in resolved.ns_carres if taker_team == 0 else resolved.ew_carres:
                taker_declarations += _carre_points(carre)
        else:
            for seq in resolved.ns_sequences if defender_team == 0 else resolved.ew_sequences:
                defender_declarations += _sequence_points(seq)
            for carre in resolved.ns_carres if defender_team == 0 else resolved.ew_carres:
                defender_declarations += _carre_points(carre)

    # Check capot: taker won all 8 tricks
    is_capot = all(
        trick_winner_seat(trick, trump) is not None and
        team_of(trick_winner_seat(trick, trump)) == taker_team
        for trick in state.completed_tricks
    ) if state.completed_tricks else False

    messages: list[str] = []

    if is_capot:
        messages.append("Capot!")
        taker_total = CAPOT_BASE + taker_declarations + taker_belote
        defender_total = defender_belote
        return ScoringBreakdown(
            taker_team=taker_team,
            taker_card_pts=0, defender_card_pts=0,
            raw_taker_card_pts=taker_card_pts, raw_defender_card_pts=defender_card_pts,
            last_trick_team=last_trick_team,
            taker_declarations=taker_declarations,
            defender_declarations=defender_declarations,
            taker_belote=taker_belote,
            defender_belote=defender_belote,
            taker_total=taker_total,
            defender_total=defender_total,
            is_capot=True, is_failed=False,
            messages=tuple(messages),
        )

    # Check bid failure
    is_failed = taker_card_pts < defender_card_pts

    if is_failed:
        messages.append("Chute! (bid failed)")
        taker_total = taker_belote
        defender_total = TOTAL_POINTS + defender_declarations + defender_belote + taker_declarations
    else:
        taker_total = taker_card_pts + taker_declarations + taker_belote
        defender_total = defender_card_pts + defender_declarations + defender_belote

    return ScoringBreakdown(
        taker_team=taker_team,
        taker_card_pts=taker_card_pts if not is_failed else 0,
        defender_card_pts=defender_card_pts if not is_failed else 0,
        raw_taker_card_pts=taker_card_pts,
        raw_defender_card_pts=defender_card_pts,
        last_trick_team=last_trick_team,
        taker_declarations=taker_declarations,
        defender_declarations=defender_declarations,
        taker_belote=taker_belote,
        defender_belote=defender_belote,
        taker_total=taker_total,
        defender_total=defender_total,
        is_capot=False, is_failed=is_failed,
        messages=tuple(messages),
    )


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

    # Create RoundScore for history
    if breakdown.taker_team == 0:
        round_score = RoundScore(
            taker_team=0,
            ns_card_pts=breakdown.taker_card_pts,
            ew_card_pts=breakdown.defender_card_pts,
            ns_decl_pts=breakdown.taker_declarations,
            ew_decl_pts=breakdown.defender_declarations,
            ns_belote_pts=breakdown.taker_belote,
            ew_belote_pts=breakdown.defender_belote,
            ns_total=breakdown.taker_total,
            ew_total=breakdown.defender_total,
            is_failed=breakdown.is_failed,
            is_capot=breakdown.is_capot,
        )
    else:
        round_score = RoundScore(
            taker_team=1,
            ns_card_pts=breakdown.defender_card_pts,
            ew_card_pts=breakdown.taker_card_pts,
            ns_decl_pts=breakdown.defender_declarations,
            ew_decl_pts=breakdown.taker_declarations,
            ns_belote_pts=breakdown.defender_belote,
            ew_belote_pts=breakdown.taker_belote,
            ns_total=breakdown.defender_total,
            ew_total=breakdown.taker_total,
            is_failed=breakdown.is_failed,
            is_capot=breakdown.is_capot,
        )

    new_history = state.score_history + (round_score,)

    # Determine if game is over
    if ns >= state.target or ew >= state.target:
        from .game import Phase as P
        phase = P.GAME_OVER
    else:
        from .game import Phase as P
        phase = P.DEAL

    # Rotate dealer
    from .game import replace as dataclass_replace
    return dataclass_replace(
        state,
        team_scores=new_scores,
        dealer=state.dealer.next_seat(),
        phase=phase,
        trump=None,
        taker=None,
        current_trick=(),
        completed_tricks=(),
        last_trick_winner=None,
        bids=(),
        bidder_index=0,
        bid_suits=(),
        round_scores=(0, 0),
        current_round_points=(0, 0),
        score_history=new_history,
        declarations=(),
        declarations_resolved=False,
        announced=None,
        belote_tracker=(False, False),
        first_trick_done=False,
    )


def get_declarations(state: GameState) -> tuple[Declaration, ...]:
    """Pre-calculate all declarations from initial hands."""
    if state.trump is None:
        return ()

    decls_per_seat: dict[Seat, dict[str, object]] = {}
    for seat in Seat:
        # If we have initial_hands, use them; otherwise use current hand (during bidding)
        hand = state.initial_hands[seat.value] if any(state.initial_hands) else state.hand_of(seat)
        if not hand:
            continue
            
        seqs = detect_sequences(hand)
        carres = detect_carres(hand)
        has_belote = detect_belote(hand, state.trump)
        decls_per_seat[seat] = {
            "sequences": seqs,
            "carres": carres,
            "belote": has_belote,
        }

    resolved = resolve_declarations(decls_per_seat, state.trump)
    scoring_team = resolved.scoring_team

    all_decls: list[Declaration] = []
    
    # We only care about sequences and carres if they actually score
    if scoring_team is not None:
        for seat in Seat:
            if team_of(seat) == scoring_team:
                decls = decls_per_seat[seat]
                for seq in decls.get("sequences", []): # type: ignore[attr-defined]
                    all_decls.append(Declaration(seat, "sequence", seq))
                for carre in decls.get("carres", []): # type: ignore[attr-defined]
                    all_decls.append(Declaration(seat, "carre", carre))

    # Belote is separate from sequence scoring
    if resolved.ns_belote:
        # Find which NS seat has it
        for s in (Seat.SOUTH, Seat.NORTH):
            if decls_per_seat[s].get("belote"):
                all_decls.append(Declaration(s, "belote"))
                
    if resolved.ew_belote:
        for s in (Seat.EAST, Seat.WEST):
            if decls_per_seat[s].get("belote"):
                all_decls.append(Declaration(s, "belote"))

    return tuple(all_decls)
