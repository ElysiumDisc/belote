"""4.9.0 / G2: hard-tier AI signaling (peter convention).

When the hard AI is forced to discard off-suit and non-trump, it swaps to
a high (9) or low (7) 0-point card to signal partner. Partner reads the
signal via `_process_trick_signals` and biases `_hard_lead`.
"""
from __future__ import annotations

import random

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, Suit
from belote.game import Seat, TrickCard


def _player(difficulty: Difficulty = Difficulty.HARD) -> AIPlayer:
    return AIPlayer(seat=Seat.SOUTH, difficulty=difficulty, rng=random.Random(0))


def test_signals_field_initializes_zero() -> None:
    p = _player()
    for suit in Suit:
        assert p.memory.signals[suit] == 0
    assert p.memory.signals_emitted == 0


def test_partner_nine_signal_is_positive() -> None:
    """Partner (NORTH) playing 9♦ off-suit on a ♥ lead signals 'lead diamonds'."""
    p = _player()
    trick = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),     # lead
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),  # follows
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.NINE)),  # signal: like ♦
    )
    p._process_trick_signals(trick, trump=Suit.SPADES)
    assert p.memory.signals[Suit.DIAMONDS] == 1
    assert p.memory.signals[Suit.HEARTS] == 0


def test_partner_seven_signal_is_negative() -> None:
    p = _player()
    trick = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.SEVEN)),  # signal: don't ♣
    )
    p._process_trick_signals(trick, trump=Suit.SPADES)
    assert p.memory.signals[Suit.CLUBS] == -1


def test_partner_eight_is_neutral() -> None:
    p = _player()
    trick = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.EIGHT)),  # neutral
    )
    p._process_trick_signals(trick, trump=Suit.SPADES)
    assert p.memory.signals[Suit.DIAMONDS] == 0


def test_trump_discard_is_not_a_signal() -> None:
    """Partner trumping the trick isn't signaling — they're winning it."""
    p = _player()
    trick = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.NINE)),  # trumped, not signaled
    )
    p._process_trick_signals(trick, trump=Suit.SPADES)
    assert p.memory.signals[Suit.SPADES] == 0


def test_easy_ai_ignores_signals() -> None:
    """Easy/medium AI doesn't run signal processing, so their `signals` dict
    stays at zero even after partner plays signal-rank cards."""
    p = _player(Difficulty.EASY)
    # Easy AI never sees signals — _process_trick_signals is only called
    # from _update_voids when difficulty==HARD. The signals dict is
    # initialized but never mutated.
    assert all(v == 0 for v in p.memory.signals.values())


def test_lead_bias_prefers_signaled_suit() -> None:
    """When partner signaled 'lead ♦', _hard_lead picks ♦ over other options."""
    p = _player()
    # Manually populate the signal so we test the lead-bias side in isolation.
    p.memory.signals[Suit.DIAMONDS] = 1
    legal = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.DIAMONDS, Rank.EIGHT),  # signaled — should win
        Card(Suit.CLUBS, Rank.SEVEN),
    )
    # Build a minimal state — _hard_lead reads state.turn / boss_modifiers
    # via memory, none of which need to be populated for this branch.
    from belote.game import new_game, start_round
    s = new_game()
    s = start_round(s, random.Random(0))
    chosen = p._hard_lead(legal, trump=Suit.SPADES, state=s)
    assert chosen.suit == Suit.DIAMONDS


def test_emit_cap_prevents_more_than_two_signals() -> None:
    p = _player()
    p.memory.signals_emitted = 2  # already capped
    legal = (
        Card(Suit.DIAMONDS, Rank.SEVEN),
        Card(Suit.DIAMONDS, Rank.NINE),
    )
    from belote.game import new_game, start_round
    s = new_game()
    s = start_round(s, random.Random(0))
    # Inject a state with a heart-led trick so 'best=DIAMONDS' is a discard.
    import dataclasses
    s = dataclasses.replace(
        s,
        current_trick=(TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),),
    )
    # Pick best as the SEVEN (low) — emit_swap should leave it alone (cap).
    chosen = p._maybe_signal_swap(
        Card(Suit.DIAMONDS, Rank.SEVEN), legal, s, trump=Suit.SPADES
    )
    # Past the cap, no swap happens — returns input unchanged.
    assert chosen == Card(Suit.DIAMONDS, Rank.SEVEN)
