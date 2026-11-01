"""Seat-relabelled views of a game, for drawing the table from any seat.

The renderer and the prompts are written from SOUTH's point of view (bottom
seat, team NS). Hot-seat play needs every human to see their own hand at the
bottom, so `rotate_view(state, seat)` relabels the seats so that `seat`
becomes SOUTH — partners stay opposite, play order stays clockwise, and
team-indexed fields swap when the rotation crosses teams, so "NS" always
means the viewer's team.

A view is display/prompt-only: cards and bids are seat-independent, so a
card or bid chosen on a rotated view is applied to the real state as is.
Never feed a rotated state back into the game.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TypeVar

from ..deck import Card
from .state import Declaration, GameState, RoundScore, Seat, TrickCard

S = TypeVar("S", bound=GameState)


def _seat_map(viewer: Seat) -> dict[Seat, Seat]:
    """Real seat → displayed seat, putting `viewer` at SOUTH."""
    return {s: Seat((s.value - viewer.value) % 4) for s in Seat}


def _swap_round_score(rs: RoundScore, m: dict[Seat, Seat]) -> RoundScore:
    return replace(
        rs,
        taker_team=1 - rs.taker_team,
        ns_card_pts=rs.ew_card_pts,
        ew_card_pts=rs.ns_card_pts,
        ns_decl_pts=rs.ew_decl_pts,
        ew_decl_pts=rs.ns_decl_pts,
        ns_belote_pts=rs.ew_belote_pts,
        ew_belote_pts=rs.ns_belote_pts,
        ns_rebelote=rs.ew_rebelote,
        ew_rebelote=rs.ns_rebelote,
        ns_total=rs.ew_total,
        ew_total=rs.ns_total,
        taker_seat=m[rs.taker_seat] if rs.taker_seat is not None else None,
        tricks_ns=rs.tricks_ew,
        tricks_ew=rs.tricks_ns,
        last_trick_winner=m[rs.last_trick_winner] if rs.last_trick_winner is not None else None,
        decl_summary_ns=rs.decl_summary_ew,
        decl_summary_ew=rs.decl_summary_ns,
    )


def _relabel_round_score(rs: RoundScore, m: dict[Seat, Seat]) -> RoundScore:
    return replace(
        rs,
        taker_seat=m[rs.taker_seat] if rs.taker_seat is not None else None,
        last_trick_winner=m[rs.last_trick_winner] if rs.last_trick_winner is not None else None,
    )


def rotate_view(state: S, viewer: Seat) -> S:
    """`state` as seen from `viewer`'s chair (see module docstring)."""
    if viewer == Seat.SOUTH:
        return state
    m = _seat_map(viewer)
    crosses_teams = viewer.value % 2 == 1  # EAST/WEST views swap NS <-> EW

    def seat(s: Seat | None) -> Seat | None:
        return m[s] if s is not None else None

    def by_seat(per_seat: tuple[tuple[Card, ...], ...]) -> tuple[tuple[Card, ...], ...]:
        out: list[tuple[Card, ...]] = [()] * 4
        for s in Seat:
            out[m[s].value] = per_seat[s.value]
        return tuple(out)

    def trick(t: tuple[TrickCard, ...]) -> tuple[TrickCard, ...]:
        return tuple(TrickCard(m[tc.seat], tc.card) for tc in t)

    def pair(p: tuple[int, int]) -> tuple[int, int]:
        return (p[1], p[0]) if crosses_teams else p

    fix_score = _swap_round_score if crosses_teams else _relabel_round_score
    return replace(
        state,
        hands=by_seat(state.hands),
        initial_hands=by_seat(state.initial_hands),
        dealer=m[state.dealer],
        leader=m[state.leader],
        turn=m[state.turn],
        taker=seat(state.taker),
        current_trick=trick(state.current_trick),
        completed_tricks=tuple(trick(t) for t in state.completed_tricks),
        last_trick_winner=seat(state.last_trick_winner),
        declarations=tuple(Declaration(m[d.seat], d.kind, d.detail) for d in state.declarations),
        team_scores=pair(state.team_scores),
        current_round_points=pair(state.current_round_points),
        score_history=tuple(fix_score(rs, m) for rs in state.score_history),
        belote_holders={suit: m[s] for suit, s in state.belote_holders.items()},
        belote_announcer=seat(state.belote_announcer),
    )
