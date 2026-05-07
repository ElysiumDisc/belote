from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from .config import GLOBAL_CONFIG
from .deck import Card, Rank, Suit
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
    reset_round_fields,
    team_of,
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


def get_declaration_points(decls: list[Sequence | Carre]) -> int:
    """Calculate point value for a list of sequences or carres."""
    pts = 0
    for d in decls:
        if isinstance(d, Sequence):
            pts += _SEQUENCE_POINTS.get(d.length, 0)
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
    return _CARRE_POINTS[_VALUE_TO_RANK[carre.rank]]


def _sequence_points(seq: Sequence) -> int:
    return _SEQUENCE_POINTS.get(seq.length, 0)


def resolve_declarations(
    decls_per_seat: dict[Seat, SeatDeclarations],
    trump: Suit | None,
) -> ResolvedDeclarations:
    """Resolve declarations per §3.7."""
    ns_seqs: list[Sequence] = []
    ew_seqs: list[Sequence] = []
    ns_carres: list[Carre] = []
    ew_carres: list[Carre] = []
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


def is_capot(state: GameState, tricks: list[tuple[TrickCard, ...]] | None = None) -> int | None:
    """Check if either team won all 8 tricks. Returns team index (0=NS, 1=EW) or None."""
    all_tricks = tricks if tricks is not None else list(state.completed_tricks)
    if not all_tricks or len(all_tricks) < 8:
        return None

    se_trump = state.boss_modifiers.seven_eight_trump
    is_sa = state.contract == "sans_atout"
    first_winner = trick_winner_seat(all_tricks[0], state.trump, se_trump, is_sa)
    if first_winner is None:
        return None
    winning_team = team_of(first_winner)

    for trick in all_tricks[1:]:
        winner = trick_winner_seat(trick, state.trump, se_trump, is_sa)
        if winner is None or team_of(winner) != winning_team:
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


def _calculate_base_points(state: GameState, trump: Suit | None) -> tuple[int, int]:
    """Calculate raw card points per team, considering boss modifiers.

    `trump=None` is the Sans Atout case. `card_points(c, None)` already returns
    the SA non-trump scale, so the inner arithmetic is unchanged.
    """
    taker_team = team_of(state.taker) if state.taker is not None else 0
    taker_pts = 0
    defender_pts = 0
    is_sa = state.contract == "sans_atout"

    kings_zero = state.boss_modifiers.kings_zero
    tens_zero = state.boss_modifiers.tens_zero
    ban_clubs = state.boss_modifiers.ban_clubs

    def get_points(card: Card, t: Suit | None) -> int:
        if kings_zero and card.rank == Rank.KING:
            return 0
        if tens_zero and card.rank == Rank.TEN:
            return 0
        if ban_clubs and card.suit == Suit.CLUBS:
            return 0
        return card_points_fn(card, t)  # type: ignore[arg-type]

    for trick in state.completed_tricks:
        winner = trick_winner_seat(
            trick, trump, state.boss_modifiers.seven_eight_trump, is_sa
        )
        if winner is None:
            continue

        if ban_clubs and any(tc.card.suit == Suit.CLUBS for tc in trick):
            trick_pts = 0
        else:
            trick_pts = sum(get_points(tc.card, trump) for tc in trick)

        if team_of(winner) == taker_team:
            taker_pts += trick_pts
        else:
            defender_pts += trick_pts

    return taker_pts, defender_pts


def _apply_scoring_modifiers(
    state: GameState, taker_pts: int, defender_pts: int
) -> tuple[int, int, list[str]]:
    """Apply complex boss scoring modifiers (Compétition, Reine Noire)."""
    messages: list[str] = []
    trump = state.trump
    is_sa = state.contract == "sans_atout"
    taker_team = team_of(state.taker) if state.taker is not None else 0

    # Boss: La Competition (Separate scoring) — applies under any active
    # contract, including Sans Atout (trump=None).
    if state.boss_modifiers.separate_scoring and state.contract is not None:
        scores = {Seat.SOUTH: 0, Seat.NORTH: 0, Seat.EAST: 0, Seat.WEST: 0}
        kings_zero = state.boss_modifiers.kings_zero
        tens_zero = state.boss_modifiers.tens_zero
        ban_clubs = state.boss_modifiers.ban_clubs

        def get_p(card: Card, t: Suit | None) -> int:
            if kings_zero and card.rank == Rank.KING:
                return 0
            if tens_zero and card.rank == Rank.TEN:
                return 0
            if ban_clubs and card.suit == Suit.CLUBS:
                return 0
            return card_points_fn(card, t)  # type: ignore[arg-type]

        for trick in state.completed_tricks:
            winner = trick_winner_seat(
                trick, trump, state.boss_modifiers.seven_eight_trump, is_sa
            )
            if winner is None:
                continue
            tp = 0 if (ban_clubs and trick[0].card.suit == Suit.CLUBS) else sum(get_p(tc.card, trump) for tc in trick)
            scores[winner] += tp

        # Add 10 de der to individual winner
        if state.last_trick_winner in scores:
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
        for trick in state.completed_tricks:
            winner = trick_winner_seat(
                trick, trump, state.boss_modifiers.seven_eight_trump, is_sa
            )
            if winner is not None and any(tc.card == qs for tc in trick):
                if team_of(winner) == taker_team:
                    taker_pts -= 25
                else:
                    defender_pts -= 25
        messages.append("Reine Noire: -25 points for capture!")

    return taker_pts, defender_pts, messages


def score_round(state: GameState) -> ScoringBreakdown:
    """Score the completed round per official rules."""
    # An active contract has either a trump suit set or contract=="sans_atout"
    # (the only legal case where trump is None mid-game). Pre-existing tests
    # build states with `trump=Suit.X` and `contract=None` — those still score
    # via the trump check.
    contract_active = state.trump is not None or state.contract == "sans_atout"
    if not contract_active or state.taker is None:
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

    trump = state.trump
    taker_team = team_of(state.taker)
    defender_team = 1 - taker_team

    # 1. Base Card Points
    taker_card_pts, defender_card_pts = _calculate_base_points(state, trump)

    # 2. Last trick bonus
    last_trick_winner = state.last_trick_winner
    last_trick_team: int | None = None
    if last_trick_winner is not None and not state.boss_modifiers.no_dix_de_der:
        last_trick_team = team_of(last_trick_winner)
        if last_trick_team == taker_team:
            taker_card_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS
        else:
            defender_card_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS

    # 3. Apply complex scoring modifiers
    taker_card_pts, defender_card_pts, messages = _apply_scoring_modifiers(
        state, taker_card_pts, defender_card_pts
    )

    # 4. Detect declarations from stored initial hands
    decls_per_seat = _detect_all_declarations(state, trump)
    resolved = resolve_declarations(decls_per_seat, trump)

    # 5. Compute belote points. Belote is disabled under Sans Atout / Tout
    # Atout (no unique K+Q-of-trump) — `belote_holders` is empty post-bid in
    # those contracts, so this path naturally collapses.
    belote_holder = state.belote_holders.get(trump) if trump is not None else None
    taker_belote = 0
    defender_belote = 0
    taker_rebelote = False
    defender_rebelote = False

    no_belote = state.boss_modifiers.no_belote or bool(
        state._joker_state.get("no_belote_rebelote")
    )
    if belote_holder is not None and not no_belote:
        holder_team = team_of(belote_holder)
        points = 0
        is_rebelote = state.belote_tracker[1]
        if is_rebelote:
            points = GLOBAL_CONFIG.REBELOTE_POINTS
        elif state.belote_tracker[0]:
            points = GLOBAL_CONFIG.BELOTE_POINTS

        if holder_team == taker_team:
            taker_belote = points
            taker_rebelote = is_rebelote
        else:
            defender_belote = points
            defender_rebelote = is_rebelote

    # 6. Compute declaration points
    scoring_team = resolved.scoring_team
    taker_declarations = 0
    defender_declarations = 0

    if scoring_team is not None:
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

    # Le Marseillais deck: annonces (Tierce/Quarte/Quinte/Carré) score x2.
    if state._joker_state.get("announce_x2"):
        taker_declarations *= 2
        defender_declarations *= 2

    # Check capot
    capot_winner_team = is_capot(state)

    # Comparison Logic
    comp_taker = taker_card_pts + taker_declarations
    comp_defender = defender_card_pts + defender_declarations

    is_failed = False
    is_litige = False
    litige_points_awarded = 0
    taker_total = 0
    defender_total = 0

    if capot_winner_team is not None:
        messages.append("Capot!")
        if capot_winner_team == taker_team:
            taker_total = (
                GLOBAL_CONFIG.CAPOT_BASE
                + taker_declarations
                + defender_declarations
                + taker_belote
                + state.litige_points
            )
            defender_total = defender_belote
        else:
            is_failed = True
            defender_total = (
                GLOBAL_CONFIG.CAPOT_BASE
                + defender_declarations
                + taker_declarations
                + defender_belote
                + state.litige_points
            )
            taker_total = taker_belote

        return ScoringBreakdown(
            taker_team=taker_team,
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
        )

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
        if state.contract == "sans_atout":
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS_SANS_ATOUT
        elif state.contract == "tout_atout":
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS_TOUT_ATOUT
        else:
            chute_total = GLOBAL_CONFIG.TOTAL_POINTS
        defender_total = (
            chute_total
            + GLOBAL_CONFIG.LAST_TRICK_BONUS
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
        t_tricks = 0
        se_trump = state.boss_modifiers.seven_eight_trump
        is_sa_local = state.contract == "sans_atout"
        for trick in state.completed_tricks:
            w = trick_winner_seat(trick, trump, se_trump, is_sa_local)
            if w is not None and team_of(w) == taker_team:
                t_tricks += 1

        defender_tricks = 8 - t_tricks
        if t_tricks > defender_tricks:
            taker_total = 0
            messages.append("Malédiction: Taker won more tricks!")
        elif defender_tricks > t_tricks:
            defender_total = 0
            messages.append("Malédiction: Defense won more tricks!")

    return ScoringBreakdown(
        taker_team=taker_team,
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

    # Trick counts per team across the played round.
    se_trump = state.boss_modifiers.seven_eight_trump
    is_sa = state.contract == "sans_atout"
    tricks_ns = 0
    tricks_ew = 0
    for trick in state.completed_tricks:
        winner = trick_winner_seat(trick, state.trump, se_trump, is_sa)
        if winner is None:
            continue
        if team_of(winner) == 0:
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

    common_kwargs = dict(
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

    # Create RoundScore for history
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
            **common_kwargs,
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
            **common_kwargs,
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
    if state.trump is None and state.contract != "sans_atout":
        return ()

    decls_per_seat = _detect_all_declarations(state, state.trump)
    resolved = resolve_declarations(decls_per_seat, state.trump)
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
