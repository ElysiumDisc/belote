"""Playing a card: trick resolution, belote/rebelote announcements, live
round points and dynamic-trump rotation (`play_card`)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..config import GLOBAL_CONFIG
from ..deck import Card, Contract, Rank, Suit
from .legal import (
    _current_trick_winner,
    legal_cards,
    trick_winner_seat,
)
from .state import (
    GameState,
    IllegalMoveError,
    Phase,
    S,
    Seat,
    TrickCard,
    team_of,
)


@dataclass(frozen=True, slots=True)
class _PlayContext:
    """3.7.1 (D1): bundle of pre-computed values used across play_card helpers.

    Built once at the top of `play_card`; threaded into the per-section
    helpers so they don't each re-derive the same fields off GameState.
    Internal — no public consumers.
    """

    state: GameState
    trump: Suit | None
    is_sa: bool
    se_trump: bool


def _record_belote_announcement(
    ctx: _PlayContext, card: Card
) -> tuple[tuple[bool, bool], Seat | None, Suit | None, str | None]:
    """Update belote_tracker / belote_announcer / belote_trump if the played
    card triggers a belote or rebelote announcement.

    Returns (belote_tracker, belote_announcer, belote_trump, announced_message).

    L'Anarchie note (3.9.3): `belote_trump` locks in the trump suit *at the
    moment of the first announcement*. The rebelote half then matches the K/Q
    play against that captured suit, not against the rotated `ctx.trump`.
    Without this, playing K-trump in trick 2 and Q-old-trump in trick 3 (after
    L'Anarchie rotates trump at tricks_count % 2 == 0) would silently drop
    the rebelote.
    """
    state = ctx.state
    belote_tracker = list(state.belote_tracker)
    belote_announcer = state.belote_announcer
    belote_trump = state.belote_trump
    announced: str | None = None

    # Once first-belote has fired we lock onto `belote_trump`; otherwise track
    # the current trump (which is also what belote_holders is keyed by at
    # round start, before any rotation).
    effective_trump = belote_trump if belote_tracker[0] else ctx.trump

    if (
        effective_trump
        and state.belote_holders.get(effective_trump) == state.turn
        and not state.variants.no_belote
    ):
        is_k_q = card.rank in (Rank.KING, Rank.QUEEN) and card.suit == effective_trump
        if is_k_q:
            if not belote_tracker[0]:
                belote_tracker[0] = True
                # Capture the announcing seat *and* the trump at that moment.
                # The seat survives L'Anarchie rotation via belote_announcer;
                # the trump survives via belote_trump (3.9.3).
                belote_announcer = state.turn
                belote_trump = effective_trump
                announced = "Belote!"
            elif not belote_tracker[1]:
                belote_tracker[1] = True
                announced = "Rebelote!"
    return (belote_tracker[0], belote_tracker[1]), belote_announcer, belote_trump, announced


def _resolve_trick_winner(ctx: _PlayContext, new_trick: tuple[TrickCard, ...]) -> Seat:
    """Determine the trick winner, applying the La Rupture override.

    La Rupture (`no_consecutive_team_wins`): if the natural winner is on the
    same team as the previous trick's winner, swing the trick to the best
    card of the other team. Raises AssertionError if `trick_winner_seat`
    returns None (invariant violation — 4 cards + trump is set under PLAYING).
    """
    state = ctx.state
    winner = trick_winner_seat(new_trick, ctx.trump, ctx.se_trump, ctx.is_sa)

    if state.variants.no_consecutive_team_wins and state.completed_tricks:
        # Use the cached resolved winner (state.last_trick_winner), not the
        # raw trick_winner_seat result from completed_tricks[-1]. play_card
        # stores the *resolved* winner, so reading from state keeps the
        # Rupture chain consistent with compute_trick_winners (used in final
        # scoring). Pre-3.8.1 the two paths drifted on trick 3+ whenever
        # Rupture flipped trick N-1.
        last_winner = state.last_trick_winner
        if last_winner and winner and team_of(winner) == team_of(last_winner):
            other_team_cards = [tc for tc in new_trick if team_of(tc.seat) != team_of(last_winner)]
            if other_team_cards and (ctx.trump or ctx.is_sa):
                best_other = _current_trick_winner(
                    other_team_cards, ctx.trump, new_trick[0].card.suit, ctx.se_trump, ctx.is_sa
                )
                if best_other:
                    winner = best_other

    if winner is None:
        # Unreachable: trick has 4 cards and trump is set (PLAYING phase
        # guarantees both). Surface this as a hard error instead of papering
        # over what would be state corruption.
        raise AssertionError(
            "trick_winner_seat returned None for a complete 4-card trick — "
            "GameState invariant violated."
        )
    return winner


def _compute_live_round_points(
    ctx: _PlayContext,
    new_trick: tuple[TrickCard, ...],
    winner: Seat,
    tricks_count: int,
) -> tuple[int, int]:
    """Live HUD running total: trick points + dix-de-der on trick 8.

    Delegates per-trick points to `scoring.trick_card_points` (canonical
    helper that already applies every boss zero-rank flag, `ban_clubs`,
    and the seven_eight_trump scale) so the HUD cannot drift from the
    eventual round score under multi-boss combos.
    """
    state = ctx.state
    if state.contract is not None:
        # Local import to break the scoring → game cycle.
        from ..scoring import trick_card_points

        trick_pts: int = trick_card_points(state, new_trick)
    else:
        trick_pts = 0

    ns_pts, ew_pts = state.current_round_points
    if team_of(winner) == 0:
        ns_pts += trick_pts
    else:
        ew_pts += trick_pts

    # Last trick bonus (suppressed by Le Zéro Final boss).
    if tricks_count == 8 and not state.variants.no_dix_de_der:
        if team_of(winner) == 0:
            ns_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS
        else:
            ew_pts += GLOBAL_CONFIG.LAST_TRICK_BONUS
    return ns_pts, ew_pts


def _rotate_dynamic_trump(ctx: _PlayContext, tricks_count: int) -> Suit | None:
    """L'Anarchie boss: rotate trump every 2 tricks (suppressed under SA and TA).

    Tout Atout has no single trump suit to rotate away from; rotating would
    silently turn it into a one-suit game while still scoring it as TA.
    """
    state = ctx.state
    if (
        state.variants.dynamic_trump
        and state.contract not in (Contract.SANS_ATOUT, Contract.TOUT_ATOUT)
        and tricks_count % 2 == 0
        and tricks_count < 8
    ):
        possible = [s for s in Suit if s != ctx.trump and s.is_card_suit]
        return state._rng.choice(possible)
    return ctx.trump


def play_card(state: S, card: Card) -> S:
    """Play a card. Returns new state, possibly advancing trick/round/phase.

    3.7.1 (D1): orchestrator over `_record_belote_announcement`,
    `_resolve_trick_winner`, `_compute_live_round_points`, and
    `_rotate_dynamic_trump`. Behaviour unchanged from 3.6.0.
    """
    legal = legal_cards(state, state.turn)
    if card not in legal:
        raise IllegalMoveError(f"Card {card} is not a legal move for {state.turn.name}")

    # Remove card from the playing seat's hand.
    t = state.turn.value
    old_hand = state.hands[t]
    idx = old_hand.index(card)
    new_hand = old_hand[:idx] + old_hand[idx + 1 :]
    new_hands = state.hands[:t] + (new_hand,) + state.hands[t + 1 :]

    new_trick = state.current_trick + (TrickCard(state.turn, card),)

    ctx = _PlayContext(
        state=state,
        trump=state.trump,
        is_sa=state.contract == Contract.SANS_ATOUT,
        se_trump=state.variants.seven_eight_trump,
    )

    # Belote/Rebelote announcement; resets the announced popup each play so it
    # fires exactly once per Belote-or-Rebelote event.
    belote_tracker, belote_announcer, belote_trump, announced = _record_belote_announcement(
        ctx, card
    )

    # Mid-trick: just advance the turn.
    if len(new_trick) != 4:
        next_turn = state.turn.next_seat()
        return replace(
            state,
            hands=tuple(new_hands),
            current_trick=new_trick,
            turn=next_turn,
            announced=announced,
            belote_tracker=belote_tracker,
            belote_announcer=belote_announcer,
            belote_trump=belote_trump,
        )

    # Trick complete: resolve winner (honouring La Rupture override).
    winner = _resolve_trick_winner(ctx, new_trick)

    new_completed = state.completed_tricks + (new_trick,)
    new_trick_trumps = state.trick_trumps + (ctx.trump,)
    tricks_count = len(new_completed)

    new_round_points = _compute_live_round_points(ctx, new_trick, winner, tricks_count)
    current_trump = _rotate_dynamic_trump(ctx, tricks_count)

    # Round complete after 8 tricks → SCORING phase.
    if tricks_count >= 8:
        return replace(
            state,
            hands=tuple(new_hands),
            current_trick=(),
            completed_tricks=new_completed,
            trick_trumps=new_trick_trumps,
            last_trick_winner=winner,
            leader=winner,
            turn=winner,
            phase=Phase.SCORING,
            announced=announced,
            belote_tracker=belote_tracker,
            belote_announcer=belote_announcer,
            belote_trump=belote_trump,
            first_trick_done=True,
            current_round_points=new_round_points,
            trump=current_trump,
        )

    # Next trick led by the winner.
    first_trick_done = state.first_trick_done or tricks_count >= 1
    return replace(
        state,
        hands=tuple(new_hands),
        current_trick=(),
        completed_tricks=new_completed,
        trick_trumps=new_trick_trumps,
        last_trick_winner=winner,
        leader=winner,
        turn=winner,
        phase=Phase.PLAYING,
        announced=announced,
        belote_tracker=belote_tracker,
        belote_announcer=belote_announcer,
        belote_trump=belote_trump,
        first_trick_done=first_trick_done,
        current_round_points=new_round_points,
        trump=current_trump,
    )


def clear_announced(state: S) -> S:
    return replace(state, announced=None)
