"""Card and trick points under the active rule variants (boss zero-rank
flags, banned clubs), and capot detection."""

from __future__ import annotations

from ..deck import Card, Contract, Rank, Suit
from ..deck import card_points as card_points_fn
from ..game import (
    GameState,
    Seat,
    TrickCard,
    compute_trick_winners,
    team_of,
)
from ..variants import RuleVariants


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


# ── Zero-rank / ban-clubs helpers (3.6.0 audit M1+M2) ───────────────────────
# Single source of truth for boss zero-rank flags. Three sites used to inline
# this with subtle drift risk: every new zero-rank flag had to be added in
# three places or the HUD running total would silently disagree with the
# final round score. Use these helpers from every scoring path.


def _trick_zeroed_by_ban_clubs(trick: tuple[TrickCard, ...], bm: RuleVariants) -> bool:
    """``ban_clubs`` zeros the entire trick if ANY card is a club. Matches
    the rule in `_calculate_base_points` — earlier the separate-scoring
    branch checked only the lead card and silently awarded points for
    off-lead clubs."""
    return bm.ban_clubs and any(tc.card.suit == Suit.CLUBS for tc in trick)


def _card_points_with_zero_ranks(card: Card, trump: Suit | None, bm: RuleVariants) -> int:
    """Per-card point value after applying every active zero-rank boss flag.

    When a new zero-rank flag is added to RuleVariants, this is the only
    site that needs to learn about it. Also propagates `seven_eight_trump`
    to `card_points` for correctness even though current point tables zero
    those cards anyway."""
    r = card.rank
    if bm.kings_zero and r == Rank.KING:
        return 0
    if bm.tens_zero and r == Rank.TEN:
        return 0
    if bm.aces_zero and r == Rank.ACE:
        return 0
    if bm.jacks_zero and r == Rank.JACK:
        return 0
    if bm.ban_clubs and card.suit == Suit.CLUBS:
        return 0
    return card_points_fn(card, trump, bm.seven_eight_trump)


def card_points_with_modifiers(card: Card, trump: Suit | None, bm: RuleVariants) -> int:
    """Public helper: per-card point value with active zero-rank boss flags.

    Mirrors `trick_card_points` (per-trick canonical helper) at the per-card
    level. Bidding heuristics (`ai.py`) call this to honor zero-rank bosses
    when evaluating Tout Atout / Sans Atout / regular-suit bid strength —
    pre-3.9.3 the AI used raw `card_points` and overbid on rank-suppressed
    hands.
    """
    return _card_points_with_zero_ranks(card, trump, bm)


def _trick_points_with_modifiers(
    trick: tuple[TrickCard, ...], trump: Suit | None, bm: RuleVariants
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
    return _trick_points_with_modifiers(trick, state.trump, state.variants)
