"""3.0.0 replay analyzer tests."""

from __future__ import annotations

import random

from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard
from belote.replay import DecisionReport, analyze_round, summarize


def test_summarize_empty_returns_no_decisions() -> None:
    assert "No decisions" in summarize([])


def test_summarize_format() -> None:
    a = DecisionReport(1, Card(Suit.HEARTS, Rank.ACE), Card(Suit.HEARTS, Rank.ACE), True)
    b = DecisionReport(2, Card(Suit.SPADES, Rank.SEVEN), Card(Suit.SPADES, Rank.JACK), False)
    out = summarize([a, b])
    assert "1/2" in out
    assert "50" in out


def test_analyze_round_skips_non_south_turns() -> None:
    """If the state's turn isn't South, the decision is ignored."""
    state = GameState(
        hands=((Card(Suit.HEARTS, Rank.ACE),), (), (), ()),
        trump=Suit.SPADES,
        turn=Seat.EAST,  # not south
        phase=Phase.PLAYING,
        current_trick=(TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),),
    )
    out = analyze_round([(state, Card(Suit.HEARTS, Rank.ACE))])
    assert out == []


def test_analyze_round_returns_one_report_per_south_decision() -> None:
    """A simple state where South has only one card must produce one report
    where chosen == suggested == that single card."""
    only = Card(Suit.HEARTS, Rank.ACE)
    state = GameState(
        hands=((only,), (), (), ()),
        trump=Suit.SPADES,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    out = analyze_round([(state, only)])
    assert len(out) == 1
    assert out[0].chosen == only
    assert out[0].matched is True


def test_analyze_round_deterministic_under_seeded_rng() -> None:
    """3.3.2: `analyze_round` must thread the caller's seeded RNG into the
    Hard AI so the same decisions reproduce. Pre-3.3.2 the constructor
    fell back to an unseeded `random.Random()`, so the SA fallback path
    (`_hard_play` → `_easy_play` → `rng.choice(legal)`) returned a
    different suggested card between runs on the same data.
    """
    # Sans Atout state with multiple legal cards. `_hard_play` falls through
    # to `_easy_play` under SA (trump is None) → `self._rng.choice(legal)`
    # is the only thing picking the suggested card; an unseeded RNG makes
    # the report non-reproducible.
    hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.JACK),
    )
    state = GameState(
        hands=(hand, (), (), ()),
        trump=None,
        contract="sans_atout",
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    chosen = hand[0]

    reports_a = analyze_round([(state, chosen)], rng=random.Random(42))
    reports_b = analyze_round([(state, chosen)], rng=random.Random(42))
    reports_c = analyze_round([(state, chosen)], rng=random.Random(42))
    assert reports_a == reports_b == reports_c

    # Different seed may or may not pick the same card — but each seed
    # must be self-consistent.
    reports_d = analyze_round([(state, chosen)], rng=random.Random(7))
    reports_e = analyze_round([(state, chosen)], rng=random.Random(7))
    assert reports_d == reports_e


# ---------------------------------------------------------------------------
# 3.3.3 T2 — Replay round-trip / seeded-round determinism
#
# Trip-wires for any future regression that re-introduces an unseeded RNG
# into the round flow (3.3.1 caught it in AIPlayer.__init__, 3.3.2 caught
# it in replay.analyze_round, 3.3.3 catches it in BelAtro boss selection).
# A failure here means the same seed no longer reproduces the same round
# — ghost runs become unreplayable.
# ---------------------------------------------------------------------------


def test_play_card_is_pure_under_fixed_decision_sequence() -> None:
    """If we record the exact cards played in a seeded round, replaying
    those cards into a fresh GameState (built from the same seed) reaches
    an identical final state. This pins play_card as a pure function of
    (state, card) — the property replay reconstruction depends on.
    """
    from belote.deck import Suit
    from belote.game import (
        Phase,
        legal_cards,
        new_game,
        place_bid,
        play_card,
        start_round,
    )

    seed = 42

    # First pass: drive the round and record each (turn, card) decision.
    rng = random.Random(seed)
    state = start_round(new_game(), rng)
    state = place_bid(state, Suit.SPADES)
    history: list = []
    while state.phase == Phase.PLAYING:
        legal = legal_cards(state, state.turn)
        card = rng.choice(legal)
        history.append(card)
        state = play_card(state, card)
    final_a = state

    # Second pass: rebuild from the same seed, replay the recorded decisions.
    rng_b = random.Random(seed)
    state_b = start_round(new_game(), rng_b)
    state_b = place_bid(state_b, Suit.SPADES)
    for card in history:
        state_b = play_card(state_b, card)
    final_b = state_b

    assert final_a.team_scores == final_b.team_scores
    assert final_a.completed_tricks == final_b.completed_tricks
    assert final_a.belote_tracker == final_b.belote_tracker
    assert final_a.belote_announcer == final_b.belote_announcer
    assert final_a.last_trick_winner == final_b.last_trick_winner
    # Hands should all be empty at end of round.
    for h in final_a.hands:
        assert h == ()
    for h in final_b.hands:
        assert h == ()


def test_seeded_round_reproduces_identical_card_sequence() -> None:
    """Stronger property: under a fixed seed, two independent runs of the
    same round (start_round → place_bid → drive via rng.choice on legal)
    produce identical card sequences. This is what the 3.3.1 AI-RNG fix
    and the 3.3.2 replay-RNG fix promised — pin it from below.
    """
    from belote.deck import Suit
    from belote.game import (
        Phase,
        legal_cards,
        new_game,
        place_bid,
        play_card,
        start_round,
    )

    def drive(seed: int) -> list:
        rng = random.Random(seed)
        state = start_round(new_game(), rng)
        state = place_bid(state, Suit.HEARTS)
        cards: list = []
        while state.phase == Phase.PLAYING:
            legal = legal_cards(state, state.turn)
            card = rng.choice(legal)
            cards.append(card)
            state = play_card(state, card)
        return cards

    a = drive(1234)
    b = drive(1234)
    assert a == b, "Seeded round produced different card sequences across runs"
    assert len(a) == 32, f"Expected 32 cards played, got {len(a)}"
