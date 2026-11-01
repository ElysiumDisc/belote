"""Round scoring: the `ScoringBreakdown`, contract made/failed (litige,
capot, coinche multipliers) and applying a round to the game score."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import GLOBAL_CONFIG
from ..deck import Card, Contract, Rank, Suit
from ..game import (
    GameState,
    Phase,
    RoundScore,
    Seat,
    compute_trick_winners,
    per_trick_trumps,
    reset_round_fields,
    team_of,
)
from .announcements import (
    ResolvedDeclarations,
    _carre_points,
    _decl_short_label,
    _detect_all_declarations,
    _sequence_points,
    resolve_declarations,
)
from .tricks import (
    _trick_points_with_modifiers,
    is_capot,
)


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
    bm = state.variants

    if winners is None:
        winners = compute_trick_winners(state, trump, is_sa)

    trumps = per_trick_trumps(state, trump, len(state.completed_tricks))
    for trick, winner, t_trump in zip(state.completed_tricks, winners, trumps, strict=True):
        if winner is None:
            continue
        trick_pts = _trick_points_with_modifiers(trick, t_trump, bm)
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
    if state.variants.separate_scoring and state.contract is not None:
        scores = {Seat.SOUTH: 0, Seat.NORTH: 0, Seat.EAST: 0, Seat.WEST: 0}
        bm = state.variants
        trumps = per_trick_trumps(state, trump, len(state.completed_tricks))
        for trick, winner, t_trump in zip(state.completed_tricks, winners, trumps, strict=True):
            if winner is None:
                continue
            scores[winner] += _trick_points_with_modifiers(trick, t_trump, bm)

        # Add 10 de der to individual winner (suppressed by Le Zéro Final).
        if state.last_trick_winner in scores and not state.variants.no_dix_de_der:
            scores[state.last_trick_winner] += GLOBAL_CONFIG.LAST_TRICK_BONUS

        if taker_team == 0:
            taker_pts = max(scores[Seat.SOUTH], scores[Seat.NORTH])
            defender_pts = max(scores[Seat.EAST], scores[Seat.WEST])
        else:
            taker_pts = max(scores[Seat.EAST], scores[Seat.WEST])
            defender_pts = max(scores[Seat.SOUTH], scores[Seat.NORTH])
        messages.append("Compétition: Higher individual score used!")

    # Boss: La Reine Noire (Queen of Spades penalty)
    if state.variants.queen_spades_penalty:
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
    # 4.8.2 (B5): pin the invariant that `belote_announcer` and
    # `belote_tracker[0]` advance in lockstep — game.py:_record_belote_announcement
    # only assigns the announcer at the moment the tracker flips True. A state
    # with announcer set but tracker[0]=False would be a corruption from
    # replay tooling or a hand-built fixture, and the scoring branches below
    # would credit belote points despite no announcement having fired. Surface
    # this as a hard assertion rather than silently mis-scoring.
    assert state.belote_announcer is None or state.belote_tracker[0], (
        "belote_announcer set without belote_tracker[0] flipped — GameState invariant violated."
    )
    # Prefer the captured announcer seat (recorded at the moment belote was
    # declared) over re-deriving from belote_holders — under L'Anarchie the
    # current state.trump differs from the trump at announcement time, and
    # the dict lookup would miss the announcer entirely.
    if state.belote_announcer is not None:
        belote_holder: Seat | None = state.belote_announcer
    else:
        belote_holder = state.belote_holders.get(ctx.trump) if ctx.trump is not None else None

    no_belote = state.variants.no_belote or state.variants.no_belote_rebelote
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
    if state.variants.double_declarations:
        taker_declarations *= 2
        defender_declarations *= 2

    # 3.0.0 Le Mime boss: all declaration points zeroed for the round.
    if state.variants.declarations_zero:
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
    if state.variants.no_dix_de_der:
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
        if state.variants.tie_breaks_for_taker:
            messages.append("La Balance: tie awarded to taker.")
            taker_total = taker_card_pts + taker_declarations + taker_belote + state.litige_points
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
        dix_de_der = 0 if state.variants.no_dix_de_der else GLOBAL_CONFIG.LAST_TRICK_BONUS
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
    if state.variants.invert_scoring:
        t_tricks = ctx.tricks_ns if ctx.taker_team == 0 else ctx.tricks_ew
        defender_tricks = 8 - t_tricks
        if t_tricks > defender_tricks:
            taker_total = 0
            messages.append("Malédiction: Taker won more tricks!")
        elif defender_tricks > t_tricks:
            defender_total = 0
            messages.append("Malédiction: Defense won more tricks!")
        else:
            # 4-4 tie: the taker failed to break the tie under Malédiction,
            # so the curse falls on them. Treated as a contract failure flavor.
            taker_total = 0
            messages.append("Malédiction: 4-4 tie — taker cursed!")

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
    if last_trick_winner is not None and not state.variants.no_dix_de_der:
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


def coinche_adjusted_credits(breakdown: ScoringBreakdown, coinche_level: int) -> tuple[int, int]:
    """Return ``(taker_credit, defender_credit)`` after the coinche multiplier.

    4.9.0 / G1: the winning side's credit is doubled at coinche_level=1,
    quadrupled at level=2. Common-variant rule — only the winning team's points
    are multiplied. Litige rounds skip the multiplier (no winner yet; the pool
    already accrues by design).

    Shared by :func:`apply_round_score` (which stores the score) and the
    gameflow round-end animation, so the on-screen counter lands on exactly the
    value that gets stored.
    """
    coinche_mult = 2**coinche_level if coinche_level > 0 else 1
    if coinche_mult > 1 and not breakdown.is_litige:
        if breakdown.is_failed:
            return breakdown.taker_total, breakdown.defender_total * coinche_mult
        return breakdown.taker_total * coinche_mult, breakdown.defender_total
    return breakdown.taker_total, breakdown.defender_total


def apply_round_score(state: GameState, breakdown: ScoringBreakdown) -> GameState:
    """Apply round scoring result to team scores and advance state."""
    taker_credit, defender_credit = coinche_adjusted_credits(breakdown, state.coinche_level)

    ns, ew = state.team_scores
    if breakdown.taker_team == 0:
        ns += taker_credit
        ew += defender_credit
    else:
        ew += taker_credit
        ns += defender_credit

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
    ns_decl_total = (
        breakdown.taker_declarations
        if breakdown.taker_team == 0
        else breakdown.defender_declarations
    )
    ew_decl_total = (
        breakdown.defender_declarations
        if breakdown.taker_team == 0
        else breakdown.taker_declarations
    )
    ns_decls = (
        tuple(_decl_short_label(d) for d in state.declarations if team_of(d.seat) == 0)
        if ns_decl_total > 0
        else ()
    )
    ew_decls = (
        tuple(_decl_short_label(d) for d in state.declarations if team_of(d.seat) == 1)
        if ew_decl_total > 0
        else ()
    )

    # 4.6.6: Unified RoundScore construction. Pre-4.6.6 this used two
    # identical-but-swapped branches for taker_team=0 vs 1, which was 50 lines
    # of redundant mapping.
    ns_is_taker = breakdown.taker_team == 0
    round_score = RoundScore(
        taker_team=breakdown.taker_team,
        ns_card_pts=breakdown.credit_taker_pts if ns_is_taker else breakdown.credit_defender_pts,
        ew_card_pts=breakdown.credit_defender_pts if ns_is_taker else breakdown.credit_taker_pts,
        ns_decl_pts=breakdown.taker_declarations
        if ns_is_taker
        else breakdown.defender_declarations,
        ew_decl_pts=breakdown.defender_declarations
        if ns_is_taker
        else breakdown.taker_declarations,
        ns_belote_pts=breakdown.taker_belote if ns_is_taker else breakdown.defender_belote,
        ew_belote_pts=breakdown.defender_belote if ns_is_taker else breakdown.taker_belote,
        ns_rebelote=breakdown.taker_rebelote if ns_is_taker else breakdown.defender_rebelote,
        ew_rebelote=breakdown.defender_rebelote if ns_is_taker else breakdown.taker_rebelote,
        ns_total=breakdown.taker_total if ns_is_taker else breakdown.defender_total,
        ew_total=breakdown.defender_total if ns_is_taker else breakdown.taker_total,
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
