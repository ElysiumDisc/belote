"""The shared round engine (`belote.round_engine`) used by classic and BelAtro."""

from __future__ import annotations

import random
import unittest.mock

import pytest

from belote.deck import Card
from belote.game import (
    BidValue,
    GameState,
    Phase,
    Seat,
    legal_bids,
    legal_cards,
    new_game,
    start_round,
)
from belote.round_engine import RoundInterrupted, RoundPolicy, play_round


class _Scripted(RoundPolicy[GameState]):
    """Takes the first legal bid (or always passes), plays the first legal card."""

    def __init__(self, always_pass: bool = False) -> None:
        self.always_pass = always_pass
        self.contracts = 0
        self.all_passes = 0
        self.cards = 0

    def choose_bid(self, state: GameState, seat: Seat) -> BidValue:
        return None if self.always_pass else legal_bids(state)[0]

    def choose_card(self, state: GameState, seat: Seat) -> tuple[Card, GameState]:
        return legal_cards(state, seat)[0], state

    def on_all_pass(self, state: GameState) -> GameState | None:
        self.all_passes += 1
        return None

    def on_contract(self, state: GameState) -> GameState:
        self.contracts += 1
        return state

    def after_card(self, before: GameState, state: GameState, seat: Seat, card: Card) -> GameState:
        self.cards += 1
        return state


def _deal(seed: int = 3) -> GameState:
    return start_round(new_game(), random.Random(seed))


def test_full_round_reaches_scoring_with_one_contract_hook() -> None:
    policy = _Scripted()
    state = play_round(_deal(), policy)
    assert state.phase == Phase.SCORING
    assert len(state.completed_tricks) == 8
    assert policy.contracts == 1
    assert policy.cards == 32


def test_all_pass_without_redeal_ends_at_deal() -> None:
    policy = _Scripted(always_pass=True)
    state = play_round(_deal(), policy)
    assert state.phase == Phase.DEAL
    assert policy.all_passes == 1
    assert policy.contracts == 0


def test_resuming_mid_play_does_not_rerun_contract_hook() -> None:
    """Classic undo restores a mid-play state. Pre-4.10.0 the classic driver
    re-ran the coinche flow (re-prompting the player and re-polling the AI
    defenders) whenever it resumed with a taker set."""
    from belote.round_engine import play_bidding

    # Bid only, then resume from the PLAYING state with a fresh policy.
    playing = play_bidding(_deal(), _Scripted())
    policy = _Scripted()
    assert playing.phase == Phase.PLAYING
    play_round(playing, policy)
    assert policy.contracts == 0
    assert policy.cards == 32


def test_interrupt_propagates() -> None:
    class _Quit(_Scripted):
        def choose_bid(self, state: GameState, seat: Seat) -> BidValue:
            raise RoundInterrupted("QUIT")

    with pytest.raises(RoundInterrupted) as info:
        play_round(_deal(), _Quit())
    assert info.value.reason == "QUIT"


def test_classic_run_bidding_on_playing_state_skips_coinche() -> None:
    """Regression for the undo-into-play coinche re-prompt (classic)."""
    from belote import gameflow
    from belote.gameflow import create_ai_players, run_bidding
    from belote.round_engine import play_bidding

    playing = play_bidding(_deal(), _Scripted())
    ai = create_ai_players({Seat.EAST: "medium", Seat.NORTH: "medium", Seat.WEST: "medium"})
    with unittest.mock.patch.object(gameflow, "_run_coinche_flow") as coinche:
        res = run_bidding(playing, unittest.mock.Mock(), ai, 0, [])
    assert res is playing
    coinche.assert_not_called()
