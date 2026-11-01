"""4.11.0 bosses — Le Contre-Attaquant and L'Huissier switch expansion-only
joker_state flags through the boss apply() path; the accumulator honors them."""

from __future__ import annotations

import random
from typing import Any

import pytest

from belote.belatro.core.scoring import (
    CONTRE_ATTAQUE_CHIPS,
    CONTRE_ATTAQUE_FLAG,
    CONTRE_ATTAQUE_MONEY,
    SEIZE_JOKER_FLAG,
    ScoreAccumulator,
)
from belote.belatro.core.state import BelatroState
from belote.belatro.engine.event_bus import BeloteAnnouncedEvent, EventBus, TrickWonEvent
from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
from belote.belatro.items.jokers.corrupted import LeDemon
from belote.belatro.items.jokers.trick_timing import LePremierSang
from belote.belatro.partner.partner_state import PartnerState
from belote.belatro.run.boss import (
    ALL_BOSS_MODIFIERS,
    BOSS_BY_ID,
    LeBrouillard,
    LeContreAttaquant,
    LHuissier,
)
from belote.deck import Suit
from belote.game import Seat, legal_bids, legal_cards
from belote.variants import RuleVariants


def _round_start(jokers: list[Any], boss: Any) -> tuple[ScoreAccumulator, BelatroState]:
    acc = ScoreAccumulator()
    acc.attach_jokers(jokers)
    state = BelatroState(hands=((), (), (), ()), _joker_state={"deck_flag": True})
    from belote.belatro.engine.round_driver import _apply_boss

    state = _apply_boss(state, boss)
    return acc, acc.trigger_round_start(state)


def test_new_bosses_registered_and_named() -> None:
    assert BOSS_BY_ID["le_contre_attaquant"] is LeContreAttaquant
    assert BOSS_BY_ID["l_huissier"] is LHuissier
    assert len(BOSS_BY_ID) == len(ALL_BOSS_MODIFIERS)
    names = [cls.name for cls in ALL_BOSS_MODIFIERS]
    assert len(names) == len(set(names))
    assert LHuissier.name != LeBrouillard.name


@pytest.mark.parametrize(
    ("boss_cls", "flag"),
    [(LeContreAttaquant, CONTRE_ATTAQUE_FLAG), (LHuissier, SEIZE_JOKER_FLAG)],
)
def test_boss_sets_joker_flag_not_core_variants(boss_cls: Any, flag: str) -> None:
    boss = boss_cls()
    assert boss.joker_flags() == {flag: True}
    assert boss.flags() == RuleVariants()  # core rules untouched
    # Older bosses have no expansion flags.
    assert LeBrouillard().joker_flags() == {}


def test_boss_flag_merges_with_existing_round_flags() -> None:
    _acc, state = _round_start([], LeContreAttaquant())
    assert state._joker_state["deck_flag"] is True
    assert state._joker_state[CONTRE_ATTAQUE_FLAG] is True


def test_contre_attaquant_steals_on_opponent_belote_and_rebelote() -> None:
    acc, state = _round_start([], LeContreAttaquant())
    chips0 = acc.current_chips(state)
    for event in (
        BeloteAnnouncedEvent(seat=Seat.EAST, is_rebelote=False),
        BeloteAnnouncedEvent(seat=Seat.EAST, is_rebelote=True),
        BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True),  # ours: no steal
    ):
        acc.process_event(state, event)
    sealed = acc.seal_round(state)
    assert sealed._chips == chips0 - 2 * CONTRE_ATTAQUE_CHIPS
    assert sealed._bonus_money == -2 * CONTRE_ATTAQUE_MONEY
    assert any("Contre-Attaquant" in line for line in acc._log)


def test_contre_attaquant_debit_is_capped_at_the_wallet() -> None:
    from belote.belatro.core.economy import Economy
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.main import BelAtroGame

    game = BelAtroGame()
    game.run = BelAtroRun(seed=3)
    game.run.economy = Economy(money=3)
    game._reconcile_bonus_money(-2 * CONTRE_ATTAQUE_MONEY)
    assert game.run.economy.money == 0


def test_no_steal_without_the_boss() -> None:
    acc = ScoreAccumulator()
    state = acc.trigger_round_start(BelatroState(hands=((), (), (), ())))
    acc.process_event(state, BeloteAnnouncedEvent(seat=Seat.WEST, is_rebelote=True))
    assert acc.seal_round(state)._bonus_money == 0


def test_huissier_seizes_only_the_leftmost_joker() -> None:
    first, second = LePremierSang(), LeDemon()
    acc, state = _round_start([first, second], LHuissier())
    acc.process_event(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(),
            trick_number=1,
            is_last=False,
            card_points=0,
            trump=Suit.HEARTS,
        ),
    )
    sealed = acc.seal_round(state)
    assert sealed._mult == pytest.approx(1.0 + 3.0)  # Le Démon only; Premier Sang seized
    assert any("seized" in line for line in acc._log)


def test_huissier_skips_round_start_jokers_too() -> None:
    from belote.belatro.items.jokers.tempo import LeRentier

    acc = ScoreAccumulator()
    acc.attach_jokers([LeRentier()])
    state = BelatroState(
        hands=((), (), (), ()), _joker_state={"current_money": 50, SEIZE_JOKER_FLAG: True}
    )
    assert acc.trigger_round_start(state)._mult == pytest.approx(1.0)


class _RandomUI(RoundUICallbacks):
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def prompt_bid(self, state: Any) -> Any:
        return self.rng.choice(legal_bids(state))

    def prompt_card(self, state: Any) -> Any:
        return self.rng.choice(legal_cards(state, state.turn)), state

    def on_card_played(self, state: Any, seat: Any, card: Any) -> None:
        pass

    def on_trick_end(self, state: Any, winner: Any, points: int) -> None:
        pass

    def on_round_end(self, breakdown: object) -> None:
        pass


@pytest.mark.parametrize("boss_cls", [LeContreAttaquant, LHuissier])
def test_new_bosses_drive_full_rounds(boss_cls: Any) -> None:
    """Integration: a whole round under each boss runs through drive_round and
    the flag reaches the round's joker_state."""
    for seed in range(4):
        acc = ScoreAccumulator()
        acc.attach_jokers([LePremierSang()])
        state = drive_round(
            bus=EventBus(),
            partner=PartnerState(),
            ui_callbacks=_RandomUI(seed),
            acc=acc,
            boss=boss_cls(),
            seed=seed,
        )
        assert next(iter(boss_cls().joker_flags())) in state._joker_state


def test_contre_attaquant_end_to_end_steal_matches_ew_belotes() -> None:
    """Over seeded rounds, every EW belote event costs exactly the steal."""
    for seed in range(40):
        acc = ScoreAccumulator()
        bus = EventBus()
        ew_belotes: list[object] = []
        bus.subscribe(
            lambda e, out=ew_belotes: (
                out.append(e)
                if isinstance(e, BeloteAnnouncedEvent) and e.seat in (Seat.EAST, Seat.WEST)
                else None
            )
        )
        state = drive_round(
            bus=bus,
            partner=PartnerState(),
            ui_callbacks=_RandomUI(seed),
            acc=acc,
            boss=LeContreAttaquant(),
            seed=seed,
        )
        assert state._bonus_money == -CONTRE_ATTAQUE_MONEY * len(ew_belotes)
