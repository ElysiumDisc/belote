from __future__ import annotations

import random

from belote.deck import card_points, deal, make_deck, shuffle
from belote.game import (
    Phase,
    legal_cards,
    new_game,
    play_card,
    start_round,
)


def test_point_conservation_property() -> None:
    """Total card points must always be 152 for any deal."""
    deck = make_deck()
    for _ in range(20):  # 20 random deals
        rng = random.Random()
        shuffled = shuffle(deck, rng)
        hands, up_card, remaining = deal(shuffled)

        # Iterate over standard card-suit trumps only; TOUT_ATOUT scores every
        # card as trump and intentionally breaks the 152 invariant.
        for trump in up_card.suit.__class__:
            if not trump.is_card_suit:
                continue
            total = card_points(up_card, trump)
            for hand in hands:
                total += sum(card_points(c, trump) for c in hand)
            total += sum(card_points(c, trump) for c in remaining)
            assert total == 152


def test_legal_moves_never_empty() -> None:
    """In PLAYING phase, legal_cards() should never return an empty tuple if hand is not empty."""
    for _ in range(5):  # 5 full game simulations
        rng = random.Random()
        state = start_round(new_game(), rng)

        # Mock taking the first suit to enter PLAYING phase
        from belote.game import place_bid

        state = place_bid(state, state.up_card.suit)

        while state.phase == Phase.PLAYING:
            seat = state.turn
            hand = state.hand_of(seat)
            # An empty hand mid-PLAYING is a deal/play bug; surface it loudly
            # rather than silently bailing.
            assert hand, (
                f"Empty hand for {seat} mid-PLAYING at trick "
                f"{len(state.completed_tricks)} — invariant violation"
            )

            legal = legal_cards(state, seat)
            assert len(legal) > 0, (
                f"No legal moves for {seat} with hand {hand} at trick {len(state.completed_tricks)}"
            )

            # Play a random legal card
            card = random.choice(legal)
            state = play_card(state, card)
