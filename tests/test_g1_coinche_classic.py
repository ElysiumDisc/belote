"""4.9.0 / G1: classic-mode coinche multiplier and AI heuristic.

`coinche_level` is per-round state; `apply_round_score` multiplies the
winning team's credit by `2 ** coinche_level`. The HARD AI defender
coinches on a strong trump hand.
"""
from __future__ import annotations

import dataclasses
import random

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Seat, new_game, start_round
from belote.scoring import ScoringBreakdown, apply_round_score


def _state(coinche_level: int = 0) -> GameState:
    s = new_game()
    s = start_round(s, random.Random(42))
    return dataclasses.replace(s, coinche_level=coinche_level, taker=Seat.SOUTH)


def _breakdown(*, taker_total: int, defender_total: int, failed: bool, taker_team: int = 0) -> ScoringBreakdown:
    # Minimal ScoringBreakdown for apply_round_score; only the fields it reads matter.
    return ScoringBreakdown(
        taker_team=taker_team,
        table_taker_pts=taker_total,
        table_defender_pts=defender_total,
        credit_taker_pts=taker_total,
        credit_defender_pts=defender_total,
        last_trick_team=taker_team,
        taker_declarations=0,
        defender_declarations=0,
        taker_belote=0,
        defender_belote=0,
        taker_rebelote=False,
        defender_rebelote=False,
        taker_total=taker_total,
        defender_total=defender_total,
        is_capot=False,
        is_failed=failed,
    )


def test_no_coinche_no_multiplier() -> None:
    s = _state(coinche_level=0)
    b = _breakdown(taker_total=100, defender_total=62, failed=False)
    new = apply_round_score(s, b)
    ns, ew = new.team_scores
    assert ns == 100 and ew == 62


def test_coinche_doubles_winning_team_credit() -> None:
    s = _state(coinche_level=1)
    # Taker (NS) wins: NS credit doubles, EW stays.
    b = _breakdown(taker_total=100, defender_total=62, failed=False)
    new = apply_round_score(s, b)
    ns, ew = new.team_scores
    assert ns == 200
    assert ew == 62


def test_coinche_failed_doubles_defender_credit() -> None:
    s = _state(coinche_level=1)
    # Failed: defender gets the bonus, not the taker.
    b = _breakdown(taker_total=0, defender_total=162, failed=True)
    new = apply_round_score(s, b)
    ns, ew = new.team_scores
    # Taker (NS) failed → defender (EW) gets ×2.
    assert ns == 0
    assert ew == 324


def test_surcoinche_quadruples() -> None:
    s = _state(coinche_level=2)
    b = _breakdown(taker_total=100, defender_total=62, failed=False)
    new = apply_round_score(s, b)
    ns, ew = new.team_scores
    assert ns == 400  # 100 × 4
    assert ew == 62


def test_coinche_level_resets_between_rounds() -> None:
    s = _state(coinche_level=1)
    b = _breakdown(taker_total=100, defender_total=62, failed=False)
    new = apply_round_score(s, b)
    # `reset_round_fields` should clear coinche_level for the next round.
    assert new.coinche_level == 0


def test_hard_ai_coinches_with_trump_jack() -> None:
    # Build a state where the AI defender (EAST) holds the trump jack.
    s = _state()
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    # Inject a hand into EAST containing the trump jack.
    hands = list(s.hands)
    hands[Seat.EAST.value] = (
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.EIGHT),
    )
    s = dataclasses.replace(s, hands=tuple(hands))
    ai = AIPlayer(seat=Seat.EAST, difficulty=Difficulty.HARD)
    assert ai.decide_coinche(s) is True


def test_easy_ai_never_coinches() -> None:
    s = _state()
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    ai = AIPlayer(seat=Seat.EAST, difficulty=Difficulty.EASY)
    # Even with a strong hand, easy never coinches.
    assert ai.decide_coinche(s) is False


def test_taker_team_member_never_coinches_own_bid() -> None:
    # NORTH (NS partner) can never coinche when SOUTH (NS) is taker at level 0.
    s = _state(coinche_level=0)
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    ai = AIPlayer(seat=Seat.NORTH, difficulty=Difficulty.HARD)
    assert ai.decide_coinche(s) is False


def test_hard_ai_taker_team_surcoinches_with_trump_jack() -> None:
    # 4.9.4: at coinche_level=1 the taker team (NORTH, partner of SOUTH-taker)
    # may surcoinche back. Mirror of test_hard_ai_coinches_with_trump_jack
    # but for the taker side.
    s = _state(coinche_level=1)
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    hands = list(s.hands)
    hands[Seat.NORTH.value] = (
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.EIGHT),
    )
    s = dataclasses.replace(s, hands=tuple(hands))
    ai = AIPlayer(seat=Seat.NORTH, difficulty=Difficulty.HARD)
    assert ai.decide_coinche(s) is True


def test_defender_cannot_re_coinche_at_level_1() -> None:
    # 4.9.4: at coinche_level=1, defenders (EAST/WEST when SOUTH is taker)
    # can NOT respond — only the taker team gets to surcoinche.
    s = _state(coinche_level=1)
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    hands = list(s.hands)
    hands[Seat.EAST.value] = (
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.ACE),
    )
    s = dataclasses.replace(s, hands=tuple(hands))
    ai = AIPlayer(seat=Seat.EAST, difficulty=Difficulty.HARD)
    assert ai.decide_coinche(s) is False


def test_no_re_surcoinche_at_level_2() -> None:
    # 4.9.4: once surcoinched, no further redoubling — return False from
    # any seat regardless of hand strength.
    s = _state(coinche_level=2)
    s = dataclasses.replace(s, trump=Suit.HEARTS, taker=Seat.SOUTH)
    for seat in (Seat.NORTH, Seat.EAST, Seat.SOUTH, Seat.WEST):
        ai = AIPlayer(seat=seat, difficulty=Difficulty.HARD)
        assert ai.decide_coinche(s) is False


def test_animation_targets_match_stored_score_under_coinche() -> None:
    """Regression: the round-end animation must target the coinche-adjusted
    credits (the same ones apply_round_score stores), not the raw breakdown
    totals. Pre-fix the counter animated to 100 while the score jumped to 200.
    """
    from belote.scoring import coinche_adjusted_credits

    for level, taker_failed in ((1, False), (2, False), (1, True)):
        s = _state(coinche_level=level)
        b = _breakdown(taker_total=0 if taker_failed else 100,
                       defender_total=162 if taker_failed else 62,
                       failed=taker_failed)
        ns_old, ew_old = s.team_scores
        taker_credit, defender_credit = coinche_adjusted_credits(b, s.coinche_level)
        if b.taker_team == 0:
            target_ns, target_ew = ns_old + taker_credit, ew_old + defender_credit
        else:
            target_ns, target_ew = ns_old + defender_credit, ew_old + taker_credit
        stored_ns, stored_ew = apply_round_score(s, b).team_scores
        assert (target_ns, target_ew) == (stored_ns, stored_ew)


def test_litige_unaffected_by_coinche_credits_helper() -> None:
    from belote.scoring import coinche_adjusted_credits

    b = _breakdown(taker_total=80, defender_total=80, failed=False)
    b = dataclasses.replace(b, is_litige=True)
    assert coinche_adjusted_credits(b, 2) == (80, 80)
