"""4.11.0 jokers — each pinned through the real ScoreAccumulator (round start →
events → sealed chips / mult / money), plus the secret unlock and the
Collection's secret handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.core.state import BelatroState
from belote.belatro.engine.event_bus import (
    BeloteAnnouncedEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)
from belote.belatro.items.base import Joker
from belote.belatro.items.jokers.rivals import (
    LaCommere,
    LaRemontee,
    LeContrebandier,
    LeRempart,
    is_honor,
)
from belote.belatro.items.jokers.tempo import (
    HORLOGER_KEY,
    LeCapitaine,
    LeJoaillier,
    LeMaitreDAtout,
    LeMarechal,
    LeMetronome,
    LePetitPoucet,
    LeRentier,
    LHorloger,
)
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.progression.save import Profile, SaveManager
from belote.belatro.progression.unlocks import UnlockTracker
from belote.deck import Card, Suit
from belote.game import Seat

S, E, N, W = Seat.SOUTH, Seat.EAST, Seat.NORTH, Seat.WEST
H, SP, D, C = Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS


def card(text: str) -> Card:
    from belote.belatro.ghost_run import parse_card

    parsed = parse_card(text)
    assert parsed is not None, text
    return parsed


@dataclass
class _Bd:
    is_failed: bool = False
    taker_total: int = 120
    defender_total: int = 42
    taker_team: int = 0


def trick(
    winner: Seat,
    cards: str = "7♣ 8♣ 9♣ 10♣",
    *,
    n: int = 2,
    leader: Seat = S,
    trump: Suit | None = H,
    last: bool = False,
    pts: int = 10,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=tuple(card(c) for c in cards.split()),
        trick_number=n,
        is_last=last,
        card_points=pts,
        trump=trump,
        leader_seat=leader,
    )


def round_end(taker: Seat | None = S, *, failed: bool = False) -> RoundEndEvent:
    return RoundEndEvent(breakdown=_Bd(is_failed=failed), taker_seat=taker, trump=H, capot=False)


def play(jokers: list[Joker], *events: object, flags: dict[str, Any] | None = None) -> Any:
    """Run `events` through a fresh accumulator; return (acc, sealed state)."""
    acc = ScoreAccumulator()
    acc.attach_jokers(jokers)
    state = acc.trigger_round_start(
        BelatroState(hands=((), (), (), ()), _joker_state=dict(flags or {}))
    )
    for event in events:
        acc.process_event(state, event)
    return acc, acc.seal_round(state)


# ── registry / content contracts ───────────────────────────────────────────

NEW_JOKERS: list[type[Joker]] = [
    LeContrebandier,
    LeMarechal,
    LeMetronome,
    LaCommere,
    LHorloger,
    LePetitPoucet,
    LeCapitaine,
    LeRempart,
    LeJoaillier,
    LeMaitreDAtout,
    LaRemontee,
    LeRentier,
]


def test_twelve_new_jokers_registered_with_unique_names() -> None:
    register_all_items()
    assert len(NEW_JOKERS) == 12
    for cls in NEW_JOKERS:
        assert registry.jokers[cls.id] is cls
        assert cls.description and cls.name and cls.cost > 0


def test_only_the_secret_joker_is_locked() -> None:
    register_all_items()
    available = registry.get_available_jokers(Profile())
    locked = [cls for cls in NEW_JOKERS if cls.id not in available]
    assert locked == [LePetitPoucet]
    assert LePetitPoucet.is_secret and LePetitPoucet.secret_hint


# ── Le Contrebandier ───────────────────────────────────────────────────────


def test_is_honor_definition() -> None:
    assert is_honor(card("J♥"), H) and is_honor(card("9♥"), H) and is_honor(card("A♥"), H)
    assert not is_honor(card("10♥"), H)  # 10 of trump is not an honor
    assert is_honor(card("10♠"), H) and is_honor(card("A♠"), H)
    assert not is_honor(card("J♠"), H)
    assert is_honor(card("10♠"), None)  # Sans Atout: A/10 everywhere
    assert is_honor(card("9♠"), Suit.TOUT_ATOUT)  # Tout Atout: J/9/A everywhere


def test_contrebandier_counts_only_opponent_honors_in_ns_tricks() -> None:
    # Leader South: S=A♠ (own honor, ignored), E=10♠ (+1), N=7♠, W=J♥ trump (+1).
    t = trick(N, "A♠ 10♠ 7♠ J♥")
    _, st = play([LeContrebandier()], t)
    assert st._mult == pytest.approx(3.0)  # 1 + 2 honors
    _, st = play([LeContrebandier()], trick(E, "A♠ 10♠ 7♠ J♥"))
    assert st._mult == pytest.approx(1.0)  # EW won it: nothing smuggled


# ── Le Maréchal / Le Métronome ─────────────────────────────────────────────


def test_marechal_x1_5_on_ns_trick_one_only() -> None:
    _, st = play([LeMarechal()], trick(N, n=1), trick(S, n=2))
    assert st._mult == pytest.approx(1.5)
    _, st = play([LeMarechal()], trick(E, n=1), trick(S, n=2))
    assert st._mult == pytest.approx(1.0)


def test_metronome_streak_grows_caps_and_resets() -> None:
    wins = [trick(S, n=i) for i in range(1, 7)]  # 0 +1 +2 +3 +3 +3
    _, st = play([LeMetronome()], *wins)
    assert st._mult == pytest.approx(1 + 0 + 1 + 2 + 3 + 3 + 3)
    events = [trick(S, n=1), trick(N, n=2), trick(E, n=3), trick(S, n=4), trick(S, n=5)]
    _, st = play([LeMetronome()], *events)
    assert st._mult == pytest.approx(1 + 1 + 1)  # tempo restarts after the lost trick


# ── La Commère ─────────────────────────────────────────────────────────────


def test_commere_profits_from_opponent_annonces_only() -> None:
    events = [
        DeclarationScoredEvent(seat=E, declaration_type="sequence", points=20),
        DeclarationScoredEvent(seat=S, declaration_type="sequence", points=50),
        DeclarationScoredEvent(seat=W, declaration_type="carre", points=0),  # Le Mime
        BeloteAnnouncedEvent(seat=W, is_rebelote=False),
        BeloteAnnouncedEvent(seat=W, is_rebelote=True),
    ]
    _, st = play([LaCommere()], *events)
    assert st._bonus_money == 4  # $2 declaration + $2 completed Belote-Rebelote


# ── L'Horloger (run-persistent) ────────────────────────────────────────────


def test_horloger_pays_at_round_start_and_ticks_on_success() -> None:
    _acc, st = play([LHorloger()], round_end(S), flags={HORLOGER_KEY: 4})
    assert st._mult == pytest.approx(1 + 0.5 * 4)
    assert st._joker_state[HORLOGER_KEY] == 5


def test_horloger_resets_on_ns_failed_contract_and_caps() -> None:
    _, st = play([LHorloger()], round_end(N, failed=True), flags={HORLOGER_KEY: 7})
    assert st._joker_state[HORLOGER_KEY] == 0
    _, st = play([LHorloger()], round_end(E, failed=False), flags={HORLOGER_KEY: 40})
    assert st._mult == pytest.approx(1 + 6.0)  # capped at +6
    assert st._joker_state[HORLOGER_KEY] == 41  # EW making it isn't our failure


def test_horloger_counter_survives_between_rounds_via_harvest() -> None:
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=1)
    run.jokers.append(LHorloger())  # harvest reads the owned jokers' persistent_keys
    _, st = play([LHorloger()], round_end(S), flags=BelAtroGame._round_flags(run))
    BelAtroGame._harvest_round_state(run, st)
    assert run.card_enhancements[HORLOGER_KEY] == 1
    flags = BelAtroGame._round_flags(run)
    _, st2 = play([LHorloger()], round_end(S), flags=flags)
    assert st2._mult == pytest.approx(1.5)
    assert st2._joker_state[HORLOGER_KEY] == 2


# ── contract / defence jokers ──────────────────────────────────────────────


def test_capitaine_needs_south_taker_success() -> None:
    assert play([LeCapitaine()], round_end(S))[1]._mult == pytest.approx(5.0)
    assert play([LeCapitaine()], round_end(N))[1]._mult == pytest.approx(1.0)
    assert play([LeCapitaine()], round_end(S, failed=True))[1]._mult == pytest.approx(1.0)


def test_rempart_rewards_a_failed_opponent_contract() -> None:
    _, st = play([LeRempart()], round_end(E, failed=True))
    assert st._mult == pytest.approx(2.0) and st._bonus_money == 3
    _, st = play([LeRempart()], round_end(S, failed=True))
    assert st._mult == pytest.approx(1.0) and st._bonus_money == 0


def test_remontee_needs_two_early_losses_then_a_made_contract() -> None:
    early = [trick(E, n=1), trick(S, n=2), trick(W, n=3), trick(S, n=4)]
    _, st = play([LaRemontee()], *early, round_end(S))
    assert st._mult == pytest.approx(3.0)
    _, st = play([LaRemontee()], *early, round_end(S, failed=True))
    assert st._mult == pytest.approx(1.0)
    _, st = play([LaRemontee()], trick(E, n=1), trick(S, n=2), trick(N, n=3), round_end(S))
    assert st._mult == pytest.approx(1.0)


# ── card-identity jokers ───────────────────────────────────────────────────


def test_maitre_d_atout_jack_and_nine_of_trump() -> None:
    # Leader South played J♥ (trump) and won.
    _, st = play([LeMaitreDAtout()], trick(S, "J♥ 7♥ 8♥ A♥"))
    assert st._mult == pytest.approx(4.0)
    # North (third card) wins with the 9 of trump.
    _, st = play([LeMaitreDAtout()], trick(N, "7♥ 8♥ 9♥ 10♥"))
    assert st._mult == pytest.approx(3.0)
    # Non-trump jack winning: nothing; Sans Atout: no trump at all.
    _, st = play([LeMaitreDAtout()], trick(S, "J♠ 7♠ 8♠ 9♠"))
    assert st._mult == pytest.approx(1.0)
    _, st = play([LeMaitreDAtout()], trick(S, "J♠ 7♠ 8♠ 9♠", trump=None))
    assert st._mult == pytest.approx(1.0)


def test_petit_poucet_small_card_wins() -> None:
    # West (4th card, leader South) wins with the 7 of trump.
    _, st = play([LePetitPoucet()], trick(W, "A♠ 10♠ K♠ 7♥"))
    assert st._mult == pytest.approx(1.0)  # an opponent's 7
    _, st = play([LePetitPoucet()], trick(N, "9♠ 10♠ K♠ 8♥", leader=W))
    assert st._mult == pytest.approx(1.5)  # leader W, N is 4th: the 8♥ trump


def test_joaillier_carre_x2_other_annonces_pay_a_dollar() -> None:
    carre = DeclarationScoredEvent(seat=N, declaration_type="carre", points=100)
    _, st = play([LeJoaillier()], carre)
    assert st._mult == pytest.approx(2.0) and st._bonus_money == 3
    tierce = DeclarationScoredEvent(seat=S, declaration_type="sequence", points=20)
    _, st = play([LeJoaillier()], tierce)
    assert st._mult == pytest.approx(1.0) and st._bonus_money == 1
    theirs = DeclarationScoredEvent(seat=E, declaration_type="carre", points=100)
    _, st = play([LeJoaillier()], theirs)
    assert st._mult == pytest.approx(1.0) and st._bonus_money == 0


def test_rentier_reads_the_pre_round_wallet() -> None:
    assert play([LeRentier()], flags={"current_money": 37})[1]._mult == pytest.approx(4.0)
    assert play([LeRentier()], flags={"current_money": 120})[1]._mult == pytest.approx(5.0)
    assert play([LeRentier()], flags={"current_money": 9})[1]._mult == pytest.approx(1.0)


# ── secret unlock + collection ─────────────────────────────────────────────


def _tracker(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> UnlockTracker:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return UnlockTracker(Profile(), SaveManager())


def test_petit_poucet_unlocks_on_dix_de_der_with_a_seven(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.on_event(trick(S, "7♠ 8♠ 9♣ 10♣", n=8, last=True, trump=H))  # S leads 7♠, wins
    assert tracker.profile.is_unlocked("le_petit_poucet")
    assert "SECRET" in tracker.drain_announcements()[0]


@pytest.mark.parametrize(
    "event",
    [
        trick(S, "7♠ 8♠ 9♣ 10♣", n=7, last=False),  # not the last trick
        trick(N, "8♠ 9♣ 7♠ 10♣", n=8, last=True),  # North, not South
        trick(S, "8♠ 7♠ 9♣ 10♣", n=8, last=True),  # South's winning card is an 8
    ],
)
def test_petit_poucet_unlock_conditions(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, event: TrickWonEvent
) -> None:
    tracker = _tracker(tmp_path, monkeypatch)
    tracker.on_event(event)
    assert not tracker.profile.is_unlocked("le_petit_poucet")


def test_collection_hides_the_secret_until_unlocked() -> None:
    from belote.belatro.ui.collection import collection_categories

    register_all_items()
    profile = Profile()
    cats, hints = collection_categories(profile)
    jokers = dict(cats)["Jokers"]
    assert LePetitPoucet not in jokers and LeContrebandier in jokers
    assert hints["Jokers"] == LePetitPoucet.secret_hint
    assert "Bosses" in dict(cats)
    profile.unlock("le_petit_poucet")
    cats, hints = collection_categories(profile)
    assert LePetitPoucet in dict(cats)["Jokers"] and "Jokers" not in hints


def test_collection_screen_shows_riddle_and_bosses_tab(tui: Any) -> None:
    from belote.belatro.ui.collection import show_collection

    register_all_items()
    profile = Profile(discovered_items=["l_huissier"])
    show_collection(tui.reader("left", "esc"), profile)
    text = tui.text
    assert "smallest card" in text
    assert "COLLECTION - Bosses" in text and "L'Huissier" in text
