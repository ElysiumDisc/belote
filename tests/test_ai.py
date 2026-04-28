from __future__ import annotations

import unittest.mock
from belote.ai import AIPlayer, Difficulty
from belote.game import GameState, Seat, Phase, TrickCard
from belote.deck import Card, Rank, Suit

def test_ai_easy_play():
    player = AIPlayer(Seat.EAST, Difficulty.EASY)
    hand = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.ACE))
    state = GameState(
        hands=[(), hand, (), ()], # type: ignore[arg-type]
        turn=Seat.EAST,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS
    )
    # Easy AI should pick a random legal card
    # We mock rng to ensure it picks the first one
    with unittest.mock.patch.object(player._rng, 'choice', side_effect=lambda x: x[0]):
        card = player.decide_card(state)
        assert card == Card(Suit.HEARTS, Rank.SEVEN)

def test_ai_medium_bid():
    player = AIPlayer(Seat.EAST, Difficulty.MEDIUM)
    # Give it a strong hearts hand
    hand = (
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.DIAMONDS, Rank.SEVEN),
    )
    up_card = Card(Suit.HEARTS, Rank.TEN)
    state = GameState(
        hands=[(), hand, (), ()], # type: ignore[arg-type]
        up_card=up_card,
        bidding_round=1,
        bidder_index=1,
        dealer=Seat.SOUTH
    )
    bid = player.decide_bid(state)
    assert bid == Suit.HEARTS

def test_ai_medium_play_follows_suit():
    player = AIPlayer(Seat.EAST, Difficulty.MEDIUM)
    hand = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.ACE))
    state = GameState(
        hands=[(), hand, (), ()], # type: ignore[arg-type]
        turn=Seat.EAST,
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS,
        current_trick=(TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),)
    )
    # Must follow hearts
    card = player.decide_card(state)
    assert card == Card(Suit.HEARTS, Rank.SEVEN)

def test_ai_hard_void_inference():
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    # South leads Spades, West (partner of East) doesn't follow
    trick1 = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.TEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)), # West void in Spades
    )
    state = GameState(
        hands=[(), (), (), ()],
        completed_tricks=(trick1,),
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS
    )
    player._update_voids(state)
    assert Suit.SPADES in player.memory.known_voids[Seat.WEST]
