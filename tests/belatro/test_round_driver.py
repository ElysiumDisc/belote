
from unittest.mock import MagicMock, patch

import pytest

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import EventBus, TrickWonEvent
from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
from belote.belatro.items.base import Joker, JokerResult
from belote.belatro.partner.partner_state import PartnerState
from belote.deck import Card
from belote.game import GameState, Phase, Seat


class MockUICallbacks(RoundUICallbacks):
    def prompt_bid(self, state: GameState):
        return None  # Pass
    def prompt_card(self, state: GameState):
        return state.hand_of(Seat.SOUTH)[0], state
    def on_card_played(self, state: GameState, seat: Seat, card: Card):
        pass
    def on_trick_end(self, state: GameState, winner: Seat, points: int):
        pass
    def on_round_end(self, breakdown: object):
        pass

def test_score_accumulator_chip_overflow():
    # 28. ScoreAccumulator chip overflow - Verify total handles large chip counts without float precision issues.
    acc = ScoreAccumulator()
    # Using very large integers that would exceed 53-bit float precision
    large_chips = 2**60 + 123456789
    large_mult = 10**12
    # Ensure _mult is effectively an int for our new precise get_total
    state = GameState(hands=((), (), (), ()), _chips=large_chips, _mult=float(large_mult))

    total = acc.get_total(state)

    expected = large_chips * large_mult
    assert total == expected

def test_score_accumulator_mult_zero():
    # 29. ScoreAccumulator mult ×0 edge case - If mult somehow becomes 0, verify total is 0.
    acc = ScoreAccumulator()
    state = GameState(hands=((), (), (), ()), _chips=1000, _mult=0.0)
    assert acc.get_total(state) == 0

def test_multiple_jokers_same_event():
    # 30. Multiple jokers same event - Verify all jokers fire on same TrickWonEvent and results compound correctly.
    class AddChipsJoker(Joker):
        def __init__(self, amount, name):
            self.amount = amount
            self.name = name
        def on_trick_won(self, event, state):
            return JokerResult(add_chips=self.amount)

    joker1 = AddChipsJoker(100, "J1")
    joker2 = AddChipsJoker(200, "J2")

    acc = ScoreAccumulator()
    acc.attach_jokers([joker1, joker2])

    state = GameState(hands=((), (), (), ()), _chips=0, _mult=1.0)
    event = TrickWonEvent(winner=Seat.SOUTH, cards=(), trick_number=1, is_last=False, card_points=10, trump=None)

    state = acc.update_state(state, event)

    # Base 10 + Joker1 100 + Joker2 200 = 310
    assert state._chips == 310

def test_drive_round_all_pass():
    # 43. Round driver with no bid - Verify drive_round handles all-pass gracefully and returns early.
    bus = EventBus()
    partner = PartnerState()
    ui = MockUICallbacks()
    # Force South to pass
    ui.prompt_bid = MagicMock(return_value=None)

    # We use a seed that likely leads to all-pass or we mock AI to pass
    with patch('belote.ai.AIPlayer.decide_bid', return_value=None):
        drive_round(bus=bus, partner=partner, boss=None, ui_callbacks=ui, seed=42)
    # If it reached the end without crashing, it's successful.
    # The 'all-pass' case returns early.

def test_event_bus_unsubscribe_during_emit():
    # 44. EventBus unsubscribe during emit - Verify handler can unsubscribe itself during event processing without crash.
    bus = EventBus()

    def handler1(event):
        bus.unsubscribe(handler1)
        handler1.called = True
    handler1.called = False

    def handler2(event):
        handler2.called = True
    handler2.called = False

    bus.subscribe(handler1)
    bus.subscribe(handler2)

    # This should not raise "RuntimeError: list changed size during iteration" if implemented correctly
    # Note: EventBus.emit currently uses `for h in self._handlers: h(event)`
    # In Python, this CAN raise if the list is modified.
    # Let's see if it's robust. If not, this test will fail and I might need to suggest a fix.
    # Actually, the requirement is to VERIFY it handles it.

    event = TrickWonEvent(winner=Seat.SOUTH, cards=(), trick_number=1, is_last=False, card_points=0, trump=None)

    try:
        bus.emit(event)
    except RuntimeError:
        pytest.fail("EventBus.emit raised RuntimeError when handler unsubscribed itself")

    assert handler1.called
    assert handler2.called
    assert len(bus._handlers) == 1
    assert handler1 not in bus._handlers

def test_boss_modifier_patch_persistence():
    # 45. Boss modifier patch persistence - Verify PatchedGameState patches survive across getattr/setattr calls.
    from belote.belatro.engine.modifier_patch import PatchedGameState
    from belote.belatro.run.boss import BossModifier

    state = GameState(hands=((), (), (), ()))
    proxy = PatchedGameState(state)

    class MockBoss(BossModifier):
        id = "test"
        name = "test"
        description = "test"
        def apply(self, state_proxy):
            state_proxy._invert_scoring = True
            # Test that we can read it back from proxy
            assert state_proxy._invert_scoring is True
            # Test that we can read something else from base state
            assert state_proxy.phase == Phase.DEAL
            return state_proxy

    MockBoss().apply(proxy)

    assert proxy._invert_scoring is True
    patches = dict(object.__getattribute__(proxy, "_patches"))
    assert "boss_modifiers" in patches
    assert patches["boss_modifiers"].invert_scoring is True
