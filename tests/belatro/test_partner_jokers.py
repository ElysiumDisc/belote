"""3.7.1 (D2) — focused coverage for the partner-joker matrix.

Pre-3.7.1 the partner-joker modules (`passive`, `risky`, `shaper`) were only
exercised via shallow smoke-tests in `test_belatro.py`. This file adds the
per-joker matrix:

    - happy path: correct seat / condition → expected JokerResult
    - non-trigger path: wrong seat / wrong condition → None
    - state reset: on_round_start clears state so round 2 behaves identically

Partner jokers explicitly key on the *partner seat* (Seat.NORTH for the
human player), NOT the team — they are the deliberate complement of
L'Accumulateur (which scores team-wide). Tests verify per-joker that
EAST/WEST trick wins are correctly ignored.
"""

from __future__ import annotations

from belote.belatro.engine.event_bus import (
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)
from belote.belatro.items.partner_jokers.passive import LaSymbiose, LeMiroir, LeRelais
from belote.belatro.items.partner_jokers.risky import LAventurier, LeMartyr, LeParasite
from belote.belatro.items.partner_jokers.shaper import LaSentinelleP, LeCalculateur, LeGenereux
from belote.deck import Card, Rank, Suit
from belote.game import Seat

# ── Test helpers ──────────────────────────────────────────────────────────


def _trick(
    winner: Seat = Seat.NORTH,
    trick_number: int = 1,
    cards: tuple[Card, ...] = (),
    trump: Suit | None = Suit.HEARTS,
    leader_seat: Seat = Seat.NORTH,
    is_last: bool = False,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=0,
        trump=trump,
        leader_seat=leader_seat,
    )


def _round_end() -> RoundEndEvent:
    # `breakdown` shape doesn't matter for partner jokers — none of them read it.
    return RoundEndEvent(
        breakdown=None,  # type: ignore[arg-type]
        taker_seat=Seat.SOUTH,
        trump=Suit.HEARTS,
        capot=False,
    )


# ── passive.LeMiroir ──────────────────────────────────────────────────────


def test_lemiroir_fires_on_partner_trick():
    j = LeMiroir()
    res = j.on_trick_won(_trick(winner=Seat.NORTH), {})
    assert res is not None and res.add_chips == 5


def test_lemiroir_silent_on_self_trick():
    j = LeMiroir()
    assert j.on_trick_won(_trick(winner=Seat.SOUTH), {}) is None


def test_lemiroir_silent_on_opponent_tricks():
    j = LeMiroir()
    assert j.on_trick_won(_trick(winner=Seat.EAST), {}) is None
    assert j.on_trick_won(_trick(winner=Seat.WEST), {}) is None


# ── passive.LaSymbiose ────────────────────────────────────────────────────


def test_lasymbiose_fires_on_partner_declaration():
    j = LaSymbiose()
    res = j.on_declaration(
        DeclarationScoredEvent(seat=Seat.NORTH, declaration_type="Tierce", points=20), {}
    )
    assert res is not None and res.times_mult == 1.2


def test_lasymbiose_silent_on_self_declaration():
    j = LaSymbiose()
    res = j.on_declaration(
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="Tierce", points=20), {}
    )
    assert res is None


# ── passive.LeRelais ──────────────────────────────────────────────────────


def test_lerelais_fires_once_on_partner_first_trick():
    j = LeRelais()
    state: dict = {}
    j.on_round_start(state)

    res = j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state)
    assert res is not None and res.add_chips == 15
    assert state[f"{j.id}_triggered"] is True


def test_lerelais_does_not_double_fire():
    j = LeRelais()
    state: dict = {}
    j.on_round_start(state)
    j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state)
    # Second invocation must not re-trigger (e.g. test harness replays).
    assert j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state) is None


def test_lerelais_silent_when_partner_wins_later_trick():
    j = LeRelais()
    state: dict = {}
    j.on_round_start(state)
    assert j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=2), state) is None


def test_lerelais_round_start_resets_trigger():
    j = LeRelais()
    state: dict = {}
    j.on_round_start(state)
    j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state)
    # Begin round 2 — flag must clear, so partner-first-trick fires again.
    j.on_round_start(state)
    assert state[f"{j.id}_triggered"] is False
    res = j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state)
    assert res is not None and res.add_chips == 15


# ── risky.LAventurier ─────────────────────────────────────────────────────


def test_laventurier_fires_at_three_three_threshold():
    j = LAventurier()
    state: dict = {}
    j.on_round_start(state)
    # Build up 3 South wins and 3 North wins; the 6th must trip the trigger.
    for _ in range(3):
        j.on_trick_won(_trick(winner=Seat.SOUTH), state)
    for i in range(3):
        res = j.on_trick_won(_trick(winner=Seat.NORTH), state)
        if i < 2:
            assert res is None
    assert state[f"{j.id}_south_wins"] == 3
    assert state[f"{j.id}_north_wins"] == 3
    assert state[f"{j.id}_triggered"] is True


def test_laventurier_silent_when_only_partner_reaches_three():
    j = LAventurier()
    state: dict = {}
    j.on_round_start(state)
    for _ in range(3):
        res = j.on_trick_won(_trick(winner=Seat.NORTH), state)
        assert res is None
    assert state[f"{j.id}_triggered"] is False


def test_laventurier_does_not_double_fire():
    j = LAventurier()
    state: dict = {}
    j.on_round_start(state)
    for _ in range(3):
        j.on_trick_won(_trick(winner=Seat.SOUTH), state)
    for _ in range(3):
        j.on_trick_won(_trick(winner=Seat.NORTH), state)
    # 4th north win must not re-trigger.
    assert j.on_trick_won(_trick(winner=Seat.NORTH), state) is None


# ── risky.LeMartyr ────────────────────────────────────────────────────────


def test_lemartyr_fires_when_partner_zero_tricks():
    j = LeMartyr()
    state: dict = {}
    j.on_round_start(state)
    res = j.on_round_end(_round_end(), state)
    assert res is not None and res.times_mult == 3.0


def test_lemartyr_silent_when_partner_wins_a_trick():
    j = LeMartyr()
    state: dict = {}
    j.on_round_start(state)
    j.on_trick_won(_trick(winner=Seat.NORTH), state)
    assert j.on_round_end(_round_end(), state) is None


def test_lemartyr_ignores_opponent_wins():
    j = LeMartyr()
    state: dict = {}
    j.on_round_start(state)
    j.on_trick_won(_trick(winner=Seat.EAST), state)
    j.on_trick_won(_trick(winner=Seat.WEST), state)
    # Partner still has zero wins → trigger.
    res = j.on_round_end(_round_end(), state)
    assert res is not None and res.times_mult == 3.0


# ── risky.LeParasite ──────────────────────────────────────────────────────


def test_leparasite_silent_before_third_partner_win():
    j = LeParasite()
    state: dict = {}
    j.on_round_start(state)
    assert j.on_trick_won(_trick(winner=Seat.NORTH), state) is None  # win 1
    assert j.on_trick_won(_trick(winner=Seat.NORTH), state) is None  # win 2


def test_leparasite_pays_per_trick_past_two():
    j = LeParasite()
    state: dict = {}
    j.on_round_start(state)
    j.on_trick_won(_trick(winner=Seat.NORTH), state)
    j.on_trick_won(_trick(winner=Seat.NORTH), state)
    # 3rd partner win = first payout
    res = j.on_trick_won(_trick(winner=Seat.NORTH), state)
    assert res is not None and res.add_money == 1
    res = j.on_trick_won(_trick(winner=Seat.NORTH), state)
    assert res is not None and res.add_money == 1


def test_leparasite_ignores_own_trick_wins():
    j = LeParasite()
    state: dict = {}
    j.on_round_start(state)
    for _ in range(5):
        assert j.on_trick_won(_trick(winner=Seat.SOUTH), state) is None
    assert state[f"{j.id}_north_wins"] == 0


# ── shaper.LeGenereux ─────────────────────────────────────────────────────


def test_legenereux_fires_per_partner_trick():
    j = LeGenereux()
    res = j.on_trick_won(_trick(winner=Seat.NORTH), {})
    assert res is not None and res.add_chips == 3


def test_legenereux_silent_on_own_trick():
    j = LeGenereux()
    assert j.on_trick_won(_trick(winner=Seat.SOUTH), {}) is None
    assert j.on_trick_won(_trick(winner=Seat.EAST), {}) is None


# ── shaper.LaSentinelleP ──────────────────────────────────────────────────


def test_lasentinellep_fires_when_partner_never_leads_trump():
    j = LaSentinelleP()
    state: dict = {}
    j.on_round_start(state)
    # Partner leads heart but heart is NOT trump → flag stays False.
    j.on_trick_won(
        _trick(
            winner=Seat.NORTH,
            leader_seat=Seat.NORTH,
            cards=(Card(Suit.SPADES, Rank.ACE),),
            trump=Suit.HEARTS,
        ),
        state,
    )
    res = j.on_round_end(_round_end(), state)
    assert res is not None and res.times_mult == 1.5


def test_lasentinellep_silent_when_partner_leads_trump():
    j = LaSentinelleP()
    state: dict = {}
    j.on_round_start(state)
    # Partner leads a heart (trump) → trip flag.
    j.on_trick_won(
        _trick(
            winner=Seat.NORTH,
            leader_seat=Seat.NORTH,
            cards=(Card(Suit.HEARTS, Rank.ACE),),
            trump=Suit.HEARTS,
        ),
        state,
    )
    assert state[f"{j.id}_trump_led"] is True
    assert j.on_round_end(_round_end(), state) is None


def test_lasentinellep_ignores_non_partner_trump_leads():
    j = LaSentinelleP()
    state: dict = {}
    j.on_round_start(state)
    # East leads trump — irrelevant.
    j.on_trick_won(
        _trick(
            winner=Seat.EAST,
            leader_seat=Seat.EAST,
            cards=(Card(Suit.HEARTS, Rank.ACE),),
            trump=Suit.HEARTS,
        ),
        state,
    )
    assert state[f"{j.id}_trump_led"] is False
    res = j.on_round_end(_round_end(), state)
    assert res is not None and res.times_mult == 1.5


# ── shaper.LeCalculateur ──────────────────────────────────────────────────


def test_lecalculateur_pays_per_partner_trick():
    j = LeCalculateur()
    state: dict = {}
    j.on_round_start(state)
    res = j.on_trick_won(_trick(winner=Seat.NORTH), state)
    assert res is not None and abs(res.add_mult - 0.3) < 1e-9


def test_lecalculateur_silent_on_own_trick():
    j = LeCalculateur()
    state: dict = {}
    j.on_round_start(state)
    assert j.on_trick_won(_trick(winner=Seat.SOUTH), state) is None
    assert state[f"{j.id}_north_wins"] == 0


def test_lecalculateur_round_start_resets_counter():
    j = LeCalculateur()
    state: dict = {}
    j.on_round_start(state)
    for _ in range(4):
        j.on_trick_won(_trick(winner=Seat.NORTH), state)
    assert state[f"{j.id}_north_wins"] == 4
    j.on_round_start(state)
    assert state[f"{j.id}_north_wins"] == 0
