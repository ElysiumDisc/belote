"""F8: Integration tests pinning down that Tout Atout / Sans Atout wins
actually fire the unlock counters and the corresponding jokers.

Pre-fix these unlocks were unreachable: there was no way to bid TA or SA in
classic play, so `progression/unlocks.py` could never increment the
`tout_atout_wins` / `sans_atout_wins` counters and `Le Fanatique` /
`L'Idéologue` were dead jokers. These tests exercise the end-to-end pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import (
    BidMadeEvent,
    EventBus,
    RoundEndEvent,
    TrickWonEvent,
)
from belote.belatro.items.jokers.contract import LeFanatique, LIdeologue
from belote.belatro.progression.save import Profile, SaveManager
from belote.belatro.progression.unlocks import UnlockTracker
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard
from belote.scoring import score_round


def _ns_capot_tricks(trump: Suit | None) -> tuple[tuple[TrickCard, ...], ...]:
    """Build 8 tricks where every trick is led and won by SOUTH (NS team).

    For Tout Atout (trump=Suit.TOUT_ATOUT) and Sans Atout (trump=None) alike,
    SOUTH leads each trick with the suit's Ace and the others follow with low
    cards in the same suit. Under TA the Ace isn't the master (the Jack is),
    so we use distinct suits across tricks to avoid accidental loss.
    """
    suits = [Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS]
    # Two tricks per suit: high block (A,K,Q,10) and low (J,9,8,7).
    # Under TA, J is the master — give it to SOUTH.
    tricks = []
    for suit in suits:
        # High trick: SOUTH plays the master of that suit
        master_rank = Rank.JACK if trump == Suit.TOUT_ATOUT else Rank.ACE
        # second/third/fourth ranks just need to be lower in the relevant scale
        if trump == Suit.TOUT_ATOUT:
            ordered = [Rank.JACK, Rank.NINE, Rank.ACE, Rank.TEN]
        else:
            ordered = [Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN]
        tricks.append((
            TrickCard(Seat.SOUTH, Card(suit, ordered[0])),
            TrickCard(Seat.WEST, Card(suit, ordered[1])),
            TrickCard(Seat.NORTH, Card(suit, ordered[2])),
            TrickCard(Seat.EAST, Card(suit, ordered[3])),
        ))
        # Low trick: SOUTH plays the highest of the remaining cards in the suit
        if trump == Suit.TOUT_ATOUT:
            low_ordered = [Rank.KING, Rank.QUEEN, Rank.EIGHT, Rank.SEVEN]
        else:
            low_ordered = [Rank.JACK, Rank.NINE, Rank.EIGHT, Rank.SEVEN]
        tricks.append((
            TrickCard(Seat.SOUTH, Card(suit, low_ordered[0])),
            TrickCard(Seat.WEST, Card(suit, low_ordered[1])),
            TrickCard(Seat.NORTH, Card(suit, low_ordered[2])),
            TrickCard(Seat.EAST, Card(suit, low_ordered[3])),
        ))
    assert master_rank in (Rank.JACK, Rank.ACE)  # touch _master_rank for clarity
    return tuple(tricks)


def _round_end_event(state: GameState) -> RoundEndEvent:
    breakdown = score_round(state)
    return RoundEndEvent(
        breakdown=breakdown,
        taker_seat=state.taker,
        trump=state.trump,
        capot=breakdown.is_capot,
        hand_remainder=(),
        contract=state.contract or "normal",
        coinche_level=0,
    )


@pytest.fixture
def isolated_save_manager(tmp_path: Path, monkeypatch):
    """Point SaveManager at a tmp path so the test doesn't touch real saves."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return SaveManager("belote-test")


def test_tout_atout_win_increments_unlock_counter_and_unlocks_joker(
    isolated_save_manager: SaveManager,
) -> None:
    """Pre-fix this counter was unreachable. Now: NS wins a Tout Atout round →
    `tout_atout_wins` increments and `le_fanatique` joker unlocks."""
    profile = Profile()
    tracker = UnlockTracker(profile, isolated_save_manager)
    bus = EventBus()
    tracker.subscribe_to(bus)

    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.TOUT_ATOUT,
        contract="tout_atout",
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=_ns_capot_tricks(Suit.TOUT_ATOUT),
        last_trick_winner=Seat.SOUTH,
    )
    bus.emit(_round_end_event(state))

    assert profile.stats["tout_atout_wins"] == 1
    assert profile.is_unlocked("le_fanatique")


def test_sans_atout_win_increments_unlock_counter_and_unlocks_joker(
    isolated_save_manager: SaveManager,
) -> None:
    """NS wins a Sans Atout round → `sans_atout_wins` increments and
    `l_ideologue` joker unlocks."""
    profile = Profile()
    tracker = UnlockTracker(profile, isolated_save_manager)
    bus = EventBus()
    tracker.subscribe_to(bus)

    state = GameState(
        hands=((), (), (), ()),
        trump=None,
        contract="sans_atout",
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=_ns_capot_tricks(None),
        last_trick_winner=Seat.SOUTH,
    )
    bus.emit(_round_end_event(state))

    assert profile.stats["sans_atout_wins"] == 1
    assert profile.is_unlocked("l_ideologue")


def test_failed_tout_atout_does_not_increment_counter(
    isolated_save_manager: SaveManager,
) -> None:
    """Failed (chute) TA round must NOT increment the win counter — the
    unlock condition requires a successful contract."""
    profile = Profile()
    tracker = UnlockTracker(profile, isolated_save_manager)
    bus = EventBus()
    tracker.subscribe_to(bus)

    # All tricks won by EW under TA → NS chute
    suits = [Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS]
    tricks = []
    for s in suits:
        # EAST leads with master Jack, NS gets low cards
        tricks.append((
            TrickCard(Seat.EAST, Card(s, Rank.JACK)),
            TrickCard(Seat.SOUTH, Card(s, Rank.SEVEN)),
            TrickCard(Seat.WEST, Card(s, Rank.ACE)),
            TrickCard(Seat.NORTH, Card(s, Rank.EIGHT)),
        ))
        tricks.append((
            TrickCard(Seat.EAST, Card(s, Rank.NINE)),
            TrickCard(Seat.SOUTH, Card(s, Rank.QUEEN)),  # Q < 9 under TA
            TrickCard(Seat.WEST, Card(s, Rank.TEN)),
            TrickCard(Seat.NORTH, Card(s, Rank.KING)),
        ))
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.TOUT_ATOUT,
        contract="tout_atout",
        taker=Seat.SOUTH,  # NS took the contract; but lost
        phase=Phase.SCORING,
        completed_tricks=tuple(tricks),
        last_trick_winner=Seat.EAST,
    )
    bus.emit(_round_end_event(state))

    assert profile.stats["tout_atout_wins"] == 0


def test_le_fanatique_fires_on_tout_atout_5th_plus_trick() -> None:
    """Le Fanatique gives ×1.5 mult after the 4th SOUTH-won trick of a TA
    round. Pre-fix this code path was unreachable in classic play. We exercise
    it directly via the score accumulator's event handling."""
    acc = ScoreAccumulator()
    acc.attach_jokers([LeFanatique()])

    state = GameState(hands=((), (), (), ()), _chips=0, _mult=1.0)
    # Inject contract via BidMadeEvent (matches round_driver's emission pattern).
    state = acc.update_state(
        state,
        BidMadeEvent(seat=Seat.SOUTH, trump=Suit.TOUT_ATOUT, contract="tout_atout"),
    )
    # Round-start event fires on_round_start — manually trigger by calling the joker
    LeFanatique().on_round_start(dict(state._joker_state))  # smoke

    # Six SOUTH-won tricks: tricks 5 and 6 should each multiply by 1.5.
    for trick_no in range(1, 7):
        state = acc.update_state(
            state,
            TrickWonEvent(
                winner=Seat.SOUTH,
                cards=(),
                trick_number=trick_no,
                is_last=False,
                card_points=10,
                trump=Suit.TOUT_ATOUT,
            ),
        )
    # After 6 tricks (4th and 5th and 6th win count > 4 → fire on tricks 5,6),
    # mult should have been multiplied twice by 1.5: 1.0 → 1.5 → 2.25.
    assert state._mult == pytest.approx(2.25)


def test_lideologue_fires_on_sans_atout_jacks() -> None:
    """L'Idéologue gives +18 chips per Jack in a SOUTH-won SA trick. Direct
    joker exercise (event.trump is None for SA)."""
    acc = ScoreAccumulator()
    acc.attach_jokers([LIdeologue()])

    state = GameState(hands=((), (), (), ()), _chips=0, _mult=1.0)
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(
                Card(Suit.HEARTS, Rank.JACK),
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.HEARTS, Rank.NINE),
                Card(Suit.HEARTS, Rank.EIGHT),
            ),
            trick_number=1,
            is_last=False,
            card_points=2,
            trump=None,  # SA
        ),
    )
    # One Jack captured under SA: +18 chips on top of the 2 base.
    assert state._chips == 20
