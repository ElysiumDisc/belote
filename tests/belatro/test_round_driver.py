
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


# ── A1 regression (3.4.0): BidMadeEvent must not double-fire on_bid jokers ──


def test_bid_made_event_does_not_double_fire_on_bid_under_auto_coinche() -> None:
    """Regression for the coinche-path double-fire bug.

    Before the fix, the auto_coinche boss path emitted BidMadeEvent twice for
    the winning bid: once during the bidding loop (coinche_level=0), then
    again post-coinche-resolution (coinche_level=1). Both emits fired
    `on_bid` jokers, so any joker that read coinche-related state on the bid
    event would be silently invoked twice (or with stale info on the first
    fire). The fix flags re-emits with `re_emit=True` so the accumulator
    skips on_bid firing while still updating joker_state["contract"].
    """
    from belote.belatro.run.boss import LAvocat

    # A joker that records every on_bid fire — we'll assert no fire happens
    # with coinche_level > 0, since re-emits should not invoke on_bid.
    class _BidSniffer(Joker):
        id = "bid_sniffer"
        name = "BidSniffer"
        description = "test"

        def __init__(self) -> None:
            self.fires: list[int] = []  # captured coinche_level per fire

        def on_bid(self, event, state):  # type: ignore[no-untyped-def]
            self.fires.append(event.coinche_level)

    sniffer = _BidSniffer()
    acc = ScoreAccumulator()
    acc.attach_jokers([sniffer])
    bus = EventBus()
    partner = PartnerState()

    # UI that passes on bids and plays the first legal card on every turn.
    class _LegalPlayUI(MockUICallbacks):
        def prompt_card(self, state: GameState):  # type: ignore[no-untyped-def]
            from belote.game import legal_cards

            legal = legal_cards(state, Seat.SOUTH)
            return legal[0], state

    drive_round(
        bus=bus,
        partner=partner,
        boss=LAvocat(),
        ui_callbacks=_LegalPlayUI(),
        acc=acc,
        seed=7,
    )

    # The fix must ensure no on_bid invocation carries coinche_level > 0 —
    # those only come from re-emits, which are now suppressed. Failures here
    # mean a re-emit slipped through without re_emit=True (regression).
    coinched_fires = [lvl for lvl in sniffer.fires if lvl > 0]
    assert coinched_fires == [], (
        f"on_bid fired with coinche_level>0 ({coinched_fires}) — re-emits "
        "should not invoke on_bid jokers."
    )


# ── H1 regression (3.6.0): EW AI can coinche an NS taker ────────────────────


def test_ew_should_coinche_baseline_rate() -> None:
    """The 3.6.0 EW defender heuristic must fire at the documented baseline
    (~20%) on a balanced hand and bump to ~35% on a strong defender hand.
    Verified by running it many times under a fixed seed and checking the
    fire-rate against the boundary, not by asserting a single coin flip."""
    import random

    from belote.belatro.engine.round_driver import _ew_should_coinche
    from belote.deck import Card, Rank, Suit
    from belote.game import GameState

    # Balanced (no defender holds 2+ J/A) → baseline 20% rate.
    weak_state = GameState(
        hands=(
            (),
            (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.EIGHT)),  # East
            (),
            (Card(Suit.CLUBS, Rank.SEVEN), Card(Suit.DIAMONDS, Rank.EIGHT)),  # West
        ),
    )
    rng = random.Random(1234)
    fires = sum(1 for _ in range(10_000) if _ew_should_coinche(weak_state, rng))
    # 20% ± a generous band; the heuristic is intentionally simple so this
    # is a smoke check, not a precise statistical test.
    assert 1700 <= fires <= 2300, f"baseline fire-rate out of band: {fires}/10000"

    # Strong defender (East holds 2 honours) → bumps to 35%.
    strong_state = GameState(
        hands=(
            (),
            (Card(Suit.HEARTS, Rank.JACK), Card(Suit.SPADES, Rank.ACE)),  # East
            (),
            (Card(Suit.CLUBS, Rank.SEVEN),),  # West
        ),
    )
    rng = random.Random(1234)
    fires = sum(1 for _ in range(10_000) if _ew_should_coinche(strong_state, rng))
    assert 3200 <= fires <= 3800, f"strong-hand fire-rate out of band: {fires}/10000"


def test_ew_ai_can_coinche_ns_taker_under_seed() -> None:
    """End-to-end: with the EW heuristic forced True and an NS-formed taker,
    the RoundEndEvent must carry coinche_level >= 1.

    Pre-3.6.0 there was no path that set coinche_level > 0 for NS-taker
    rounds outside of auto_coinche / start_coinched. The Libra planet
    (gated on `coinche_level > 0 AND taker on NS AND not failed`) was
    therefore unreachable in natural play. This test would have failed
    before the H1 fix."""
    from unittest.mock import patch

    from belote.game import Seat as _Seat

    class _RoundEndSniffer(Joker):
        id = "round_end_sniffer"
        name = "Sniffer"
        description = "test"

        def __init__(self) -> None:
            self.events: list[object] = []

        def on_round_end(self, event, state):  # type: ignore[no-untyped-def]
            self.events.append(event)

    sniffer = _RoundEndSniffer()
    acc = ScoreAccumulator()
    acc.attach_jokers([sniffer])

    class _SouthBidsAndPlays(MockUICallbacks):
        def prompt_bid(self, state: GameState):  # type: ignore[no-untyped-def]
            # Bid the up-card suit in round 1 (always legal); pass round 2.
            if state.bidding_round == 1 and state.up_card is not None:
                return state.up_card.suit
            return None

        def prompt_card(self, state: GameState):  # type: ignore[no-untyped-def]
            from belote.game import legal_cards

            return legal_cards(state, Seat.SOUTH)[0], state

    bus = EventBus()
    partner = PartnerState()

    with patch(
        "belote.belatro.engine.round_driver._ew_should_coinche",
        return_value=True,
    ), patch(
        "belote.ai.AIPlayer.decide_bid",
        return_value=None,
    ):
        drive_round(
            bus=bus,
            partner=partner,
            boss=None,
            ui_callbacks=_SouthBidsAndPlays(),
            acc=acc,
            seed=42,
        )

    contract_events = [e for e in sniffer.events if getattr(e, "taker_seat", None) is not None]
    assert contract_events, "expected a RoundEndEvent with a taker"
    evt = contract_events[-1]
    assert evt.taker_seat in (_Seat.NORTH, _Seat.SOUTH), (
        f"test setup: expected NS taker, got {evt.taker_seat}"
    )
    assert evt.coinche_level >= 1, (
        f"EW AI should have coinched (heuristic forced True) but "
        f"coinche_level={evt.coinche_level}"
    )


# ─── 3.7.1 D3: NS-taker player surcoinche prompt ────────────────────────────


def _drive_ns_taker_round_with_surcoinche(
    surcoinche_response: bool,
    *,
    seed: int,
    ai_surcoinches: bool,
) -> int:
    """Helper: drive a round where NS takes, EW coinches, and the player is
    asked whether to surcoinche back. Returns the final coinche_level.

    `ai_surcoinches` patches `rng.random()` post-prompt to force/skip the
    AI fallback (the 30% gated branch).
    """
    from unittest.mock import patch

    class _RoundEndSniffer(Joker):
        id = "round_end_sniffer"
        name = "Sniffer"
        description = "test"

        def __init__(self) -> None:
            self.events: list[object] = []

        def on_round_end(self, event, state):  # type: ignore[no-untyped-def]
            self.events.append(event)

    sniffer = _RoundEndSniffer()
    acc = ScoreAccumulator()
    acc.attach_jokers([sniffer])

    class _SouthBidsAndPlays(MockUICallbacks):
        def __init__(self) -> None:
            self.surcoinche_prompted = False

        def prompt_bid(self, state: GameState):  # type: ignore[no-untyped-def]
            if state.bidding_round == 1 and state.up_card is not None:
                return state.up_card.suit
            return None

        def prompt_card(self, state: GameState):  # type: ignore[no-untyped-def]
            from belote.game import legal_cards

            return legal_cards(state, Seat.SOUTH)[0], state

        def prompt_surcoinche(self, state: GameState, coincheur: Seat) -> bool:
            self.surcoinche_prompted = True
            return surcoinche_response

    ui = _SouthBidsAndPlays()
    bus = EventBus()
    partner = PartnerState()

    # Force surcoinche to be unlocked (per-run voucher gate) so the new code
    # path runs at all. The flag lives on `state._joker_state` and is set
    # via `card_enhancements`.
    enhancements = {"surcoinche_unlocked": True}

    with patch(
        "belote.belatro.engine.round_driver._ew_should_coinche",
        return_value=True,
    ), patch(
        "belote.ai.AIPlayer.decide_bid",
        return_value=None,
    ):
        # Patch rng.random so the AI-surcoinche-fallback (30%) is deterministic.
        # `rng.random` is called only after the player prompt declines.
        random_value = 0.1 if ai_surcoinches else 0.9  # <0.3 → AI surcoinches

        import random as _random

        def patched_random(self):  # type: ignore[no-untyped-def]
            return random_value

        with patch.object(_random.Random, "random", patched_random):
            drive_round(
                bus=bus,
                partner=partner,
                boss=None,
                ui_callbacks=ui,
                acc=acc,
                seed=seed,
                card_enhancements=enhancements,
            )

    assert ui.surcoinche_prompted, "prompt_surcoinche was never called"
    contract_events = [
        e for e in sniffer.events if getattr(e, "taker_seat", None) is not None
    ]
    assert contract_events, "expected a RoundEndEvent with a taker"
    return contract_events[-1].coinche_level


def test_d3_player_accepts_surcoinche_reaches_level_2() -> None:
    """Player accepts surcoinche when EW coinches NS-taker bid → coinche_level=2."""
    level = _drive_ns_taker_round_with_surcoinche(
        surcoinche_response=True, seed=42, ai_surcoinches=False
    )
    assert level == 2, f"expected surcoinche (level 2), got {level}"


def test_d3_player_declines_ai_does_not_surcoinche_stays_at_1() -> None:
    """Player declines + AI rolls > 0.3 → coinche_level stays at 1."""
    level = _drive_ns_taker_round_with_surcoinche(
        surcoinche_response=False, seed=42, ai_surcoinches=False
    )
    assert level == 1, f"expected coinche-only (level 1), got {level}"


def test_d3_player_declines_ai_surcoinches_reaches_level_2() -> None:
    """Player declines but AI fallback fires → coinche_level=2."""
    level = _drive_ns_taker_round_with_surcoinche(
        surcoinche_response=False, seed=42, ai_surcoinches=True
    )
    assert level == 2, f"expected AI-surcoinche (level 2), got {level}"


def test_d3_default_callback_returns_false() -> None:
    """Default RoundUICallbacks.prompt_surcoinche must return False (no-op)."""
    cb = MockUICallbacks()
    # MockUICallbacks inherits the default from RoundUICallbacks.
    state = GameState(hands=((), (), (), ()))
    assert cb.prompt_surcoinche(state, Seat.EAST) is False



# ── 3.8.1: boss flags must be applied before acc.trigger_round_start ──


def test_boss_flags_applied_before_trigger_round_start() -> None:
    """3.8.1 fix: round_driver previously called acc.trigger_round_start
    BEFORE boss.apply, so any joker_state field derived from
    state.boss_modifiers.X (e.g. joker_state["no_dix_de_der"]) captured the
    default value instead of the boss-patched one. The order must be
    boss.apply → trigger_round_start.

    Lock the fix: joker_state["no_dix_de_der"] must reflect the active boss
    flag after drive_round completes the round.
    """
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import EventBus
    from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
    from belote.belatro.partner.partner_state import PartnerState
    from belote.belatro.run.boss import BossModifier

    class LeZeroFinal(BossModifier):
        id = "le_zero_final_test"
        name = "Le Zéro Final (test)"
        description = "Disables Dix de Der"

        def apply(self, state: object) -> None:  # PatchedGameState
            state.patch("no_dix_de_der", True)  # type: ignore[attr-defined]

    class _NoopUI(RoundUICallbacks):
        def prompt_bid(self, state):  # type: ignore[no-untyped-def, override]
            return None  # Pass — round will exhaust bids and short-circuit.
        def prompt_card(self, state):  # type: ignore[no-untyped-def, override]
            return state.hands[state.turn.value][0], state
        def on_card_played(self, state, seat, card) -> None:  # type: ignore[no-untyped-def, override]
            pass
        def on_trick_end(self, state, winner, points) -> None:  # type: ignore[no-untyped-def, override]
            pass
        def on_round_end(self, breakdown) -> None:  # type: ignore[no-untyped-def, override]
            pass

    bus = EventBus()
    partner = PartnerState()
    captured: dict[str, object] = {}

    class _SpyAcc(ScoreAccumulator):
        def trigger_round_start(self, state):  # type: ignore[no-untyped-def, override]
            captured["no_dix_de_der"] = state.boss_modifiers.no_dix_de_der
            return super().trigger_round_start(state)

    acc = _SpyAcc(target_score=80)

    import contextlib
    # Drive may error out without a fleshed-out UI; we only care that
    # trigger_round_start was called once and observed the patched boss flag.
    with contextlib.suppress(Exception):
        drive_round(
            bus=bus,
            partner=partner,
            ui_callbacks=_NoopUI(),
            acc=acc,
            boss=LeZeroFinal(),
            target_score=80,
            seed=42,
        )

    assert captured.get("no_dix_de_der") is True, (
        "Boss flag was not applied before trigger_round_start — the joker "
        "state snapshot would see stale BossModifiers defaults."
    )


def test_drive_round_emits_to_event_bus():
    """4.6.4: drive_round must publish every event through the EventBus too.

    Pre-4.6.4 `_emit()` only called `acc.process_event()` and never
    `bus.emit()`. Consequence: the process-wide UnlockTracker subscribes to
    the bus in `belatro/main.py` but received zero events from natural play,
    silently breaking L'Exécuteur / L'Idéologue / Le Fanatique / Quinte
    Royale unlocks. Tests in `test_contract_unlocks.py` passed because they
    `bus.emit(...)` directly, bypassing `drive_round` entirely.

    Pin the integration: at minimum one BidMadeEvent reaches a bus subscriber
    after `drive_round` returns.
    """
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import BidMadeEvent, EventBus
    from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
    from belote.belatro.partner.partner_state import PartnerState

    class _PassAllUI(RoundUICallbacks):
        def prompt_bid(self, state):  # type: ignore[no-untyped-def, override]
            return None
        def prompt_card(self, state):  # type: ignore[no-untyped-def, override]
            return state.hands[state.turn.value][0], state
        def on_card_played(self, state, seat, card) -> None:  # type: ignore[no-untyped-def, override]
            pass
        def on_trick_end(self, state, winner, points) -> None:  # type: ignore[no-untyped-def, override]
            pass
        def on_round_end(self, breakdown) -> None:  # type: ignore[no-untyped-def, override]
            pass

    bus = EventBus()
    received: list[object] = []
    bus.subscribe(received.append)
    acc = ScoreAccumulator(target_score=80)

    with patch("belote.ai.AIPlayer.decide_bid", return_value=None):
        drive_round(
            bus=bus,
            partner=PartnerState(),
            ui_callbacks=_PassAllUI(),
            acc=acc,
            boss=None,
            target_score=80,
            seed=42,
        )

    assert received, (
        "drive_round did not publish any event through the EventBus — "
        "UnlockTracker subscribers would receive nothing (regression of the "
        "silently-broken-unlocks bug fixed in 4.6.4)."
    )
    assert any(isinstance(e, BidMadeEvent) for e in received), (
        "Expected at least one BidMadeEvent (every pass during bidding emits "
        f"one); only saw {[type(e).__name__ for e in received]}."
    )


def test_raising_joker_isolated_via_transactional(caplog):
    """4.6.4: a joker handler that raises mid-dispatch must NOT leak partial
    ledger mutations AND must NOT skip sibling jokers in the same event.

    Pre-4.6.4 the RoundLedger.transactional() guard was defined but never
    wired in: ScoreAccumulator.process_event() dispatched joker handlers
    without any rollback or isolation. A buggy joker that wrote a few
    chips/log lines then raised would leak those mutations and short-circuit
    every other joker subscribed to the same event.

    Lock the fix: a partial-then-raise joker leaves ledger.chips at the
    pre-handler value and the sibling joker after it still applies.
    """
    import logging

    class HalfThenRaise(Joker):
        id = "half_then_raise"
        name = "HalfThenRaise"
        description = "test fixture"
        def on_trick_won(self, event, state):
            # The joker's *handler* mutation comes back via JokerResult, so
            # raising before returning is the realistic shape. The accumulator
            # rolls back any mutations applied DURING the handler call.
            raise RuntimeError("simulated joker crash")

    class AlwaysAdds(Joker):
        id = "always_adds"
        name = "AlwaysAdds"
        description = "test fixture"
        def on_trick_won(self, event, state):
            return JokerResult(add_chips=42)

    acc = ScoreAccumulator()
    acc.attach_jokers([HalfThenRaise(), AlwaysAdds()])

    state = GameState(hands=((), (), (), ()), _chips=0, _mult=1.0)
    event = TrickWonEvent(
        winner=Seat.SOUTH, cards=(), trick_number=1,
        is_last=False, card_points=10, trump=None,
    )

    with caplog.at_level(logging.ERROR, logger="belote.belatro.core.scoring"):
        state = acc.update_state(state, event)

    # 10 (base card pts) + 42 (AlwaysAdds) — HalfThenRaise contributed nothing.
    assert state._chips == 52, (
        f"Expected sibling joker to still fire after raising joker; got "
        f"chips={state._chips} (10 base + 42 sibling expected)."
    )
    assert any(
        "HalfThenRaise" in rec.message or
        (rec.exc_info and "simulated joker crash" in str(rec.exc_info[1]))
        for rec in caplog.records
    ), "Expected the raising joker to be logged via logger.exception."
