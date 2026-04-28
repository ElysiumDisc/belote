from __future__ import annotations

import random
from belote.game import (
    GameState, Seat, Phase, start_round, new_game
)
from belote.scoring import apply_round_score, ScoringBreakdown
from belote.deck import Card, Suit, Rank

def test_apply_round_score():
    state = GameState(
        hands=[(), (), (), ()], # type: ignore[arg-type]
        team_scores=(100, 50),
        target=1000
    )
    score = ScoringBreakdown(
        taker_team=0,
        taker_card_pts=80,
        defender_card_pts=72,
        raw_taker_card_pts=80,
        raw_defender_card_pts=72,
        last_trick_team=0,
        taker_declarations=20,
        defender_declarations=0,
        taker_belote=20,
        defender_belote=0,
        taker_total=120,
        defender_total=72,
        is_failed=False,
        is_capot=False,
        messages=()
    )
    new_state = apply_round_score(state, score)
    assert new_state.team_scores == (220, 122)
    assert new_state.dealer == Seat.EAST # Dealer should rotate
    assert new_state.phase == Phase.DEAL # Ready for next round

def test_dealer_rotation_full_cycle():
    state = new_game()
    assert state.dealer == Seat.SOUTH
    
    rng = random.Random(42)
    # Mocking round end
    score = ScoringBreakdown(0,0,0,0,0,0,0,0,0,0,0,0,False,False,())
    # 1st round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.EAST
    
    # 2nd round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.NORTH
    
    # 3rd round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.WEST
    
    # 4th round
    state = start_round(state, rng)
    state = apply_round_score(state, score)
    assert state.dealer == Seat.SOUTH

def test_start_round_integrity():
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)
    
    # Check all 32 cards are present
    all_cards = list(state.remaining_cards) + [state.up_card]
    for h in state.hands:
        all_cards.extend(h)
        
    assert len(all_cards) == 32
    assert len(set(all_cards)) == 32
    
    # Initial hands should be 5 cards each
    for h in state.hands:
        assert len(h) == 5
    
    assert state.phase == Phase.BIDDING
