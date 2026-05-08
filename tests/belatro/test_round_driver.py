
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
            # 3.1.0: unprefixed name only (the underscore-strip shim was
            # removed in modifier_patch.py).
            state_proxy.invert_scoring = True
            # Test that we can read it back from proxy via the canonical path
            assert state_proxy.boss_modifiers.invert_scoring is True
            # Test that we can read something else from base state
            assert state_proxy.phase == Phase.DEAL
            return state_proxy

    MockBoss().apply(proxy)

    assert proxy.boss_modifiers.invert_scoring is True
    patches = dict(object.__getattribute__(proxy, "_patches"))
    assert "boss_modifiers" in patches
    assert patches["boss_modifiers"].invert_scoring is True


# ── B1 regression: sabotage_tricks populated for any agent_double_active source ──


class _AbortAfterCaptureError(Exception):
    """Sentinel: raised inside prompt_bid to short-circuit drive_round once the
    pre-bidding setup state has been captured."""


class _CaptureBidUI(MockUICallbacks):
    """UI that captures the state passed into prompt_bid (post-boss-apply,
    post-sabotage-trick setup) and aborts the round so we don't have to mock
    a full PLAYING phase to assert on setup. Captures from prompt_card too in
    case SOUTH isn't the first bidder and the partner personality bids first."""

    def __init__(self) -> None:
        self.captured: GameState | None = None

    def _capture_and_abort(self, state: GameState) -> None:
        if self.captured is None:
            self.captured = state
        raise _AbortAfterCaptureError

    def prompt_bid(self, state: GameState):  # type: ignore[no-untyped-def]
        self._capture_and_abort(state)

    def prompt_card(self, state: GameState):  # type: ignore[no-untyped-def]
        self._capture_and_abort(state)


def _capture_post_setup_state(boss=None, card_enhancements=None) -> GameState:  # type: ignore[no-untyped-def]
    import contextlib

    bus = EventBus()
    partner = PartnerState()
    ui = _CaptureBidUI()
    with contextlib.suppress(_AbortAfterCaptureError):
        drive_round(
            bus=bus,
            partner=partner,
            boss=boss,
            ui_callbacks=ui,
            seed=7,
            card_enhancements=card_enhancements,
        )
    assert ui.captured is not None
    return ui.captured


def test_agent_double_boss_populates_sabotage_tricks() -> None:
    """L'Agent Double boss → 3 random sabotage tricks set in _joker_state."""
    from belote.belatro.run.boss import LAgentDoubleBoss

    state = _capture_post_setup_state(boss=LAgentDoubleBoss())
    tricks = state._joker_state.get("agent_double_tricks")
    assert isinstance(tricks, frozenset)
    assert len(tricks) == 3
    assert all(1 <= t <= 8 for t in tricks)


def test_betrayal_arc_populates_late_sabotage_tricks() -> None:
    """BetrayalArc → sabotage_tricks == {4..8} ('partner sabotages from trick 4 onward').

    Pre-fix this was the bug: BetrayalArc set agent_double_active=True but the
    round_driver only populated sabotage_tricks when boss.id matched l_agent_double_boss,
    so partner never actually sabotaged.
    """
    from belote.belatro.run.boss import BetrayalArc

    state = _capture_post_setup_state(boss=BetrayalArc())
    assert state.boss_modifiers.agent_double_active is True
    assert state.boss_modifiers.agent_double_late_only is True
    assert state._joker_state.get("agent_double_tricks") == frozenset(range(4, 9))


def test_traitre_joker_sabotage_preserved_when_no_boss() -> None:
    """Le Traître joker (card_enhancement) sets a single sabotage trick that the
    flag-based dispatch must not clobber."""
    state = _capture_post_setup_state(card_enhancements={"traitre_active": True})
    assert state.boss_modifiers.agent_double_active is True
    tricks = state._joker_state.get("agent_double_tricks")
    assert isinstance(tricks, frozenset)
    assert len(tricks) == 1  # traitre's "single random trick" pattern
