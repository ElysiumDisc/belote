from __future__ import annotations

import random
from belote.deck import make_deck, shuffle, deal, card_points
from belote.game import (
    new_game, start_round, Phase, Seat, legal_cards,
    play_card, TrickCard, GameState
)

def test_point_conservation_property():
    """Total card points must always be 152 for any deal."""
    deck = make_deck()
    for _ in range(20): # 20 random deals
        rng = random.Random()
        shuffled = shuffle(deck, rng)
        hands, up_card, remaining = deal(shuffled)
        
        for trump in list(up_card.suit.__class__): # All suits
            total = card_points(up_card, trump)
            for hand in hands:
                total += sum(card_points(c, trump) for c in hand)
            total += sum(card_points(c, trump) for c in remaining)
            assert total == 152

def test_legal_moves_never_empty():
    """In PLAYING phase, legal_cards() should never return an empty tuple if hand is not empty."""
    deck = make_deck()
    for _ in range(5): # 5 full game simulations
        rng = random.Random()
        state = start_round(new_game(), rng)
        
        # Mock taking the first suit to enter PLAYING phase
        from belote.game import place_bid
        state = place_bid(state, state.up_card.suit)
        
        while state.phase == Phase.PLAYING:
            seat = state.turn
            hand = state.hand_of(seat)
            if not hand:
                # This should not happen in PLAYING before 8 tricks
                break
            
            legal = legal_cards(state, seat)
            assert len(legal) > 0, f"No legal moves for {seat} with hand {hand} at trick {len(state.completed_tricks)}"
            
            # Play a random legal card
            card = random.choice(legal)
            state = play_card(state, card)
