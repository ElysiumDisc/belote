"""H3 audit fix: EventBus has a documented round-scope invariant + clear()."""

from __future__ import annotations

from belote.belatro.engine.event_bus import EventBus, RoundEndEvent
from belote.deck import Suit
from belote.game import Seat


def _evt() -> RoundEndEvent:
    return RoundEndEvent(
        breakdown=None,
        taker_seat=Seat.SOUTH,
        trump=Suit.HEARTS,
        capot=False,
    )


def test_subscribe_and_emit_dispatches_to_handler() -> None:
    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(lambda e: seen.append(e))
    bus.emit(_evt())
    assert len(seen) == 1


def test_clear_drops_all_handlers() -> None:
    """Pre-3.5.0 there was no way to bulk-drop subscribers. `clear()` makes
    a longer-lived bus safe to re-use across rounds without leaking handlers.
    """
    bus = EventBus()
    a_calls: list[int] = []
    b_calls: list[int] = []
    bus.subscribe(lambda e: a_calls.append(1))
    bus.subscribe(lambda e: b_calls.append(1))

    bus.emit(_evt())
    assert a_calls == [1] and b_calls == [1]

    bus.clear()
    bus.emit(_evt())
    # Cleared — subsequent emit fires neither handler.
    assert a_calls == [1] and b_calls == [1]


def test_raising_subscriber_does_not_skip_siblings(caplog) -> None:
    """3.6.0 audit H3: a buggy joker on_event handler must not halt the
    rest of the round's subscribers. The bus catches Exception, logs it,
    and continues iterating. (BaseException — e.g. KeyboardInterrupt —
    is intentionally not caught so a user Ctrl-C still tears down.)"""
    bus = EventBus()
    seen_before: list[int] = []
    seen_after: list[int] = []

    def good_before(_e: object) -> None:
        seen_before.append(1)

    def boom(_e: object) -> None:
        raise RuntimeError("simulated joker crash")

    def good_after(_e: object) -> None:
        seen_after.append(1)

    bus.subscribe(good_before)
    bus.subscribe(boom)
    bus.subscribe(good_after)

    import logging
    with caplog.at_level(logging.ERROR, logger="belote.belatro.engine.event_bus"):
        bus.emit(_evt())

    assert seen_before == [1]
    assert seen_after == [1], "subscriber after a raising handler must still fire"
    assert any("simulated joker crash" in rec.message or rec.exc_info for rec in caplog.records)


def test_consecutive_rounds_use_independent_buses() -> None:
    """The current contract: drive_round() creates a fresh bus per round.
    Round 2 subscribers never see round 1 events, and vice versa.
    """
    seen_r1: list[object] = []
    seen_r2: list[object] = []

    bus_r1 = EventBus()
    bus_r1.subscribe(lambda e: seen_r1.append(e))
    bus_r1.emit(_evt())

    bus_r2 = EventBus()
    bus_r2.subscribe(lambda e: seen_r2.append(e))
    bus_r2.emit(_evt())
    bus_r2.emit(_evt())

    assert len(seen_r1) == 1
    assert len(seen_r2) == 2
    # Round 1's bus never sees round 2 events.
    assert seen_r1 != seen_r2
