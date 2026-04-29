from __future__ import annotations

import unittest.mock

from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, new_game
from belote.gameflow import create_ai_players, run_bidding, run_play
from belote.input import KeyReader


def test_run_bidding_human_takes():
    # Mocking UI and side effects
    with unittest.mock.patch('belote.gameflow.display'), \
         unittest.mock.patch('belote.gameflow.prompt_bid', return_value=Suit.HEARTS), \
         unittest.mock.patch('belote.gameflow.interruptible_sleep', return_value=False):

        state = new_game()
        # Mock deal: each player has 5 cards, 11 remaining
        hands = tuple(
            tuple(Card(Suit.SPADES, r) for r in [Rank.EIGHT, Rank.NINE, Rank.TEN, Rank.JACK, Rank.QUEEN])
            for _ in range(4)
        )
        state = GameState(
            hands=hands,
            up_card=Card(Suit.HEARTS, Rank.TEN),
            phase=Phase.BIDDING,
            turn=Seat.SOUTH,
            dealer=Seat.WEST,
            remaining_cards=tuple(Card(Suit.SPADES, Rank.SEVEN) for _ in range(11))
        )
        reader = unittest.mock.Mock(spec=KeyReader)
        history = []
        human_seats = {Seat.SOUTH}
        ai_players = create_ai_players({
            Seat.EAST: "medium",
            Seat.NORTH: "medium",
            Seat.WEST: "medium"
        }, human_seats)

        new_state = run_bidding(state, reader, ai_players, 0, history, human_seats)

        assert isinstance(new_state, GameState)
        assert new_state.phase == Phase.PLAYING
        assert new_state.trump == Suit.HEARTS
        assert new_state.taker == Seat.SOUTH

def test_run_play_8_tricks():
    # Mocking UI and side effects
    with unittest.mock.patch('belote.gameflow.display'), \
         unittest.mock.patch('belote.gameflow.patch_trick_card'), \
         unittest.mock.patch('belote.gameflow.play_sound'), \
         unittest.mock.patch('belote.gameflow.announce'):

        # Build a state at start of play
        hands = tuple(tuple(Card(Suit.HEARTS, r) for r in list(Rank)) for _ in range(4))
        state = GameState(
            hands=hands,
            phase=Phase.PLAYING,
            trump=Suit.SPADES,
            turn=Seat.SOUTH,
            taker=Seat.SOUTH
        )
        reader = unittest.mock.Mock(spec=KeyReader)
        history = []
        human_seats = set() # All AI for speed
        ai_players = create_ai_players(dict.fromkeys(Seat, "easy"), human_seats)

        # Mock AI to just pick first legal card
        for ai in ai_players.values():
            ai.decide_card = unittest.mock.Mock(side_effect=lambda s, ai=ai: s.hand_of(ai.seat)[0])

        new_state = run_play(state, reader, ai_players, 0, 0, history, human_seats)

        assert isinstance(new_state, GameState)
        assert new_state.phase == Phase.SCORING
        assert len(new_state.completed_tricks) == 8
