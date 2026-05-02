from __future__ import annotations

import pytest
from dataclasses import replace
from belote.ai import AIPlayer, Difficulty
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.belatro.items.base import Joker, JokerResult
from belote.belatro.partner.partner_state import PartnerState
from belote.belatro.partner.trust import TrustTrack
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Seat


def make_trick_event(
    winner: Seat = Seat.SOUTH,
    trick_number: int = 1,
    is_last: bool = False,
    card_points: int = 0,
    cards: tuple[Card, ...] = (),
    trump: Suit | None = None,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=trump,
    )


class TestPartnerTrust:
    # 25. AI partner forced pass (La Solitude boss)
    def test_ai_partner_forced_pass(self) -> None:
        """Verify partner always passes when _partner_forced_pass is set."""
        state = GameState(hands=((), (), (), ()))
        # Manually set the flag (usually injected by BossModifier)
        state = replace(state, _partner_forced_pass=True)
        
        # Partner of South is North
        ai = AIPlayer(Seat.NORTH, Difficulty.MEDIUM)
        bid = ai.decide_bid(state)
        assert bid is None

    # 26. AI agent double (L'Agent Double boss)
    def test_ai_agent_double_sabotage(self) -> None:
        """Verify partner plays worst card when _agent_double_active is set."""
        # We need a hand for the AI
        cards = (
            Card(Suit.SPADES, Rank.JACK),  # High rank in trump
            Card(Suit.SPADES, Rank.NINE),
            Card(Suit.SPADES, Rank.SEVEN),  # Low rank
        )
        # North is partner of South
        hands = [(), (), list(cards), ()]  # S, E, N, W
        state = GameState(hands=tuple(tuple(h) for h in hands))
        state = replace(state, trump=Suit.SPADES, _agent_double_active=True, turn=Seat.NORTH)
        
        ai = AIPlayer(Seat.NORTH, Difficulty.MEDIUM)
        played = ai.decide_card(state)
        
        # Agent Double makes partner play the worst card (lowest trick rank)
        # For SPADES trump, JACK is highest, SEVEN is lowest.
        assert played.rank == Rank.SEVEN

    # 34. Partner joker double trust
    def test_partner_joker_double_trust(self) -> None:
        """Verify partner joker effects fire twice when partner_jokers_double is True."""
        acc = ScoreAccumulator(partner_jokers_double=True)
        
        class MockPartnerJoker(Joker):
            name = "Mock Partner Joker"
            is_partner_joker = True
            def on_trick_won(self, event: object, joker_state: dict[str, object]) -> JokerResult | None:
                return JokerResult(add_chips=10)
        
        joker = MockPartnerJoker()
        acc.attach_jokers([joker])
        
        state = GameState(hands=((), (), (), ()))
        # Initial chips 0
        state = replace(state, _chips=0, _mult=1.0)
        
        evt = make_trick_event(winner=Seat.SOUTH)
        new_state = acc.update_state(state, evt)
        
        # 10 chips from original + 10 chips from double trigger = 20
        assert new_state._chips == 20

    # 35. Trust degradation
    def test_trust_degradation_difficulty(self) -> None:
        """Verify AI difficulty drops to 'easy' when trust <= 2."""
        # Test 1: Trust > 2 -> medium
        trust = TrustTrack(value=3)
        partner_state = PartnerState(trust=trust)
        assert partner_state.difficulty_for(Seat.NORTH) == "medium"
        
        # Test 2: Trust <= 2 -> easy
        trust.value = 2
        assert partner_state.difficulty_for(Seat.NORTH) == "easy"
        
        trust.value = 0
        assert partner_state.difficulty_for(Seat.NORTH) == "easy"
