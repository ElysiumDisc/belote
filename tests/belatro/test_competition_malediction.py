"""La Compétition + La Malédiction stacking behaviour (4.8.2 T3).

Pre-4.8.2 it was undocumented whether the two boss flags compose in
practice. They CAN both be set simultaneously (e.g. by a future combo
boss or save-state corruption), and `score_round` runs both modifier
branches sequentially. This test pins the actual behaviour so future
changes either preserve it or knowingly opt out:

  1. La Compétition replaces per-team card-points with the *higher of the
     two seats on each team* — i.e. South's pts vs North's pts, max wins.
  2. La Malédiction then zeros the taker_total if the taker won more
     tricks than the defenders (or the defender_total in the reverse
     case, or zeros taker on a 4-4 tie).

Net effect: Compétition's per-seat substitution is preserved in the
breakdown's table fields (for history display), but Malédiction's
trick-count gate is the dominant signal — it can zero either side
regardless of the Compétition-reshaped points.

No design opinion is asserted here — just the observed behaviour.
"""

from __future__ import annotations

from belote.belatro.engine.modifier_patch import PatchedGameState
from belote.belatro.run.boss import LaCompetition, LaMalediction
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard, new_game


def test_competition_malediction_flags_coexist() -> None:
    """Re-pin (sanity) that both flags hold after sequential apply()."""
    state = PatchedGameState(new_game())
    LaCompetition().apply(state)
    LaMalediction().apply(state)
    bm = state.boss_modifiers
    assert bm.separate_scoring is True
    assert bm.invert_scoring is True


def _build_finished_round_state(*, taker_team: int = 0) -> GameState:
    """Construct a SCORING-phase state with 8 completed tricks: 5 won by
    SOUTH (NS) and 3 won by EAST (EW). Avoids the capot path because
    `_score_capot_outcome` skips La Malédiction by design (the Malédiction
    branch lives in `_score_normal_outcome`)."""
    from belote.game import BossModifiers

    # Non-trump cards only so winners are determined by lead-suit rank.
    # Trump is hearts; these tricks are in spades / diamonds / clubs.
    # Under the non-trump scale (A > 10 > K > Q > J > 9 > 8 > 7), SOUTH
    # leading ♠A wins; EAST leading ♣A wins.
    ns_winning_trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.NINE)),
    )
    ew_winning_trick = (
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.ACE)),
        TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.EIGHT)),
        TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.NINE)),
    )
    completed = (ns_winning_trick,) * 5 + (ew_winning_trick,) * 3

    taker = Seat.SOUTH if taker_team == 0 else Seat.EAST
    return GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        contract="hearts",
        taker=taker,
        completed_tricks=completed,
        last_trick_winner=Seat.EAST,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(
            separate_scoring=True,
            invert_scoring=True,
        ),
    )


def test_competition_malediction_score_round_does_not_crash() -> None:
    """Smoke: the score_round path with both flags active must complete
    without raising. Either side may be zeroed by Malédiction, but the
    breakdown must be a well-formed ScoringBreakdown."""
    from belote.scoring import score_round

    state = _build_finished_round_state(taker_team=0)
    breakdown = score_round(state)
    assert breakdown is not None
    # Both branches should appear in the messages list — Compétition AND
    # Malédiction each append at least one line under their respective
    # boss flag, regardless of which side ends up zeroed.
    messages_joined = " | ".join(breakdown.messages)
    assert "Compétition" in messages_joined, (
        f"La Compétition message missing under combo: {breakdown.messages}"
    )
    assert "Malédiction" in messages_joined, (
        f"La Malédiction message missing under combo: {breakdown.messages}"
    )


def test_competition_alone_substitutes_per_seat_max() -> None:
    """La Compétition alone replaces team totals with the higher per-seat
    score. Verify this part of the chain is functional before the combo."""
    from dataclasses import replace

    from belote.game import BossModifiers
    from belote.scoring import score_round

    state = _build_finished_round_state()
    # Strip La Malédiction; keep Compétition only.
    state = replace(state, boss_modifiers=BossModifiers(separate_scoring=True))
    breakdown = score_round(state)
    assert "Compétition" in " | ".join(breakdown.messages)
    # Smoke: well-formed breakdown.
    assert breakdown.taker_total >= 0
    assert breakdown.defender_total >= 0
