"""
Comprehensive pytest test suite for the Belatro roguelite module.

Covers: Economy, TrustTrack, ScoreAccumulator, BelAtroRun, EventBus,
trick-timing jokers, partner jokers (passive/risky/shaper), Profile,
SaveManager, ANTE_TABLE, boss modifiers, item registry, and Shop.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from belote.deck import Card, Rank, Suit
from belote.game import Seat

if TYPE_CHECKING:
    from belote.belatro.engine.event_bus import (
        BeloteAnnouncedEvent,
        BidMadeEvent,
        DeclarationScoredEvent,
        RoundEndEvent,
        TrickWonEvent,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trick_event(
    winner: Seat = Seat.SOUTH,
    trick_number: int = 1,
    is_last: bool = False,
    card_points: int = 0,
    cards: tuple[Card, ...] = (),
    trump: Suit | None = None,
) -> TrickWonEvent:
    from belote.belatro.engine.event_bus import TrickWonEvent

    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=trump,
    )


def make_decl_event(
    seat: Seat = Seat.SOUTH, declaration_type: str = "Tierce", points: int = 20
) -> DeclarationScoredEvent:
    from belote.belatro.engine.event_bus import DeclarationScoredEvent

    return DeclarationScoredEvent(seat=seat, declaration_type=declaration_type, points=points)


def make_round_end_event(
    breakdown: Any = None,
    taker_seat: Seat = Seat.SOUTH,
    trump: Suit | None = None,
    capot: bool = False,
    hand_remainder: tuple[Card, ...] = (),
) -> RoundEndEvent:
    from belote.belatro.engine.event_bus import RoundEndEvent

    return RoundEndEvent(
        breakdown=breakdown,
        taker_seat=taker_seat,
        trump=trump,
        capot=capot,
        hand_remainder=hand_remainder,
    )


def make_bid_event(
    seat: Seat = Seat.SOUTH, trump: Suit | None = None, contract: str = "normal"
) -> BidMadeEvent:
    from belote.belatro.engine.event_bus import BidMadeEvent

    return BidMadeEvent(seat=seat, trump=trump, contract=contract)


def make_belote_event(seat: Seat = Seat.SOUTH, is_rebelote: bool = False) -> BeloteAnnouncedEvent:
    from belote.belatro.engine.event_bus import BeloteAnnouncedEvent

    return BeloteAnnouncedEvent(seat=seat, is_rebelote=is_rebelote)


# ===========================================================================
# Economy
# ===========================================================================


class TestEconomy:
    def setup_method(self) -> None:
        from belote.belatro.core.economy import Economy

        self.eco = Economy()

    def test_default_money_is_zero(self) -> None:
        assert self.eco.money == 0

    def test_add_money_increases_money(self) -> None:
        self.eco.add_money(10)
        assert self.eco.money == 10

    def test_add_money_accumulates(self) -> None:
        self.eco.add_money(5)
        self.eco.add_money(3)
        assert self.eco.money == 8

    def test_spend_money_success_returns_true(self) -> None:
        self.eco.money = 20
        result = self.eco.spend_money(15)
        assert result is True
        assert self.eco.money == 5

    def test_spend_money_exact_amount_succeeds(self) -> None:
        self.eco.money = 10
        result = self.eco.spend_money(10)
        assert result is True
        assert self.eco.money == 0

    def test_spend_money_insufficient_returns_false(self) -> None:
        self.eco.money = 5
        result = self.eco.spend_money(10)
        assert result is False
        assert self.eco.money == 5  # unchanged

    def test_spend_money_zero_always_succeeds(self) -> None:
        result = self.eco.spend_money(0)
        assert result is True

    def test_calculate_interest_rate_zero_returns_zero(self) -> None:
        self.eco.money = 100
        self.eco.interest_rate = 0
        assert self.eco.calculate_interest() == 0

    def test_calculate_interest_rate_one_basic(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=15, interest_rate=1, max_interest=5)
        # 15 // 5 * 1 = 3
        assert eco.calculate_interest() == 3

    def test_calculate_interest_capped_at_max_interest(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=100, interest_rate=1, max_interest=5)
        # 100 // 5 * 1 = 20 → capped at 5
        assert eco.calculate_interest() == 5

    def test_calculate_interest_fractional_money_floors(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=14, interest_rate=1, max_interest=10)
        # 14 // 5 = 2 → interest = 2
        assert eco.calculate_interest() == 2

    def test_process_round_end_no_overflow_gives_base(self) -> None:
        # 50 pts over target → 50 // 10 = 5
        payout = self.eco.process_round_end(50)
        assert payout == 5
        assert self.eco.money == 5

    def test_process_round_end_adds_interest(self) -> None:
        from belote.belatro.core.economy import Economy

        eco = Economy(money=10, interest_rate=1, max_interest=5)
        # 30 over → 3 base + 10//5 interest = 3 + 2 = 5
        payout = eco.process_round_end(30)
        assert payout == 5
        assert eco.money == 15

    def test_process_round_end_negative_pts_gives_zero(self) -> None:
        payout = self.eco.process_round_end(-100)
        assert payout == 0
        assert self.eco.money == 0

    def test_process_round_end_zero_pts_gives_zero_base(self) -> None:
        payout = self.eco.process_round_end(0)
        assert payout == 0


# ===========================================================================
# TrustTrack
# ===========================================================================


class TestTrustTrack:
    def setup_method(self) -> None:
        from belote.belatro.partner.trust import TrustTrack

        self.trust = TrustTrack()

    def test_initial_value_is_five(self) -> None:
        assert self.trust.value == 5

    def test_blind_beaten_adds_one(self) -> None:
        self.trust.blind_beaten()
        assert self.trust.value == 6

    def test_big_margin_win_adds_two(self) -> None:
        self.trust.big_margin_win()
        assert self.trust.value == 7

    def test_capot_together_adds_three(self) -> None:
        self.trust.capot_together()
        assert self.trust.value == 8

    def test_blind_failed_subtracts_one(self) -> None:
        self.trust.blind_failed()
        assert self.trust.value == 4

    def test_chute_subtracts_two(self) -> None:
        self.trust.chute()
        assert self.trust.value == 3

    def test_partner_passes_all_sets_zero(self) -> None:
        self.trust.partner_passes_all()
        assert self.trust.value == 0

    def test_clamp_at_maximum_ten(self) -> None:
        self.trust.value = 9
        self.trust.capot_together()  # +3 → would be 12 → clamped at 10
        assert self.trust.value == 10

    def test_clamp_at_minimum_zero(self) -> None:
        self.trust.value = 1
        self.trust.chute()  # -2 → would be -1 → clamped at 0
        assert self.trust.value == 0

    def test_blind_beaten_at_ten_stays_ten(self) -> None:
        self.trust.value = 10
        self.trust.blind_beaten()
        assert self.trust.value == 10

    def test_chute_at_zero_stays_zero(self) -> None:
        self.trust.value = 0
        self.trust.chute()
        assert self.trust.value == 0

    # --- Threshold properties ---

    def test_shares_void_info_false_below_threshold(self) -> None:
        self.trust.value = 2
        assert self.trust.shares_void_info is False

    def test_shares_void_info_true_at_threshold(self) -> None:
        self.trust.value = 3
        assert self.trust.shares_void_info is True

    def test_shares_void_info_true_above_threshold(self) -> None:
        self.trust.value = 7
        assert self.trust.shares_void_info is True

    def test_duo_contracts_available_false_below_five(self) -> None:
        self.trust.value = 4
        assert self.trust.duo_contracts_available is False

    def test_duo_contracts_available_true_at_five(self) -> None:
        self.trust.value = 5
        assert self.trust.duo_contracts_available is True

    def test_partner_jokers_double_false_below_seven(self) -> None:
        self.trust.value = 6
        assert self.trust.partner_jokers_double is False

    def test_partner_jokers_double_true_at_seven(self) -> None:
        self.trust.value = 7
        assert self.trust.partner_jokers_double is True

    def test_auto_capot_available_true_at_nine_not_used(self) -> None:
        self.trust.value = 9
        self.trust.auto_capot_used = False
        assert self.trust.auto_capot_available is True

    def test_auto_capot_available_false_if_already_used(self) -> None:
        self.trust.value = 10
        self.trust.auto_capot_used = True
        assert self.trust.auto_capot_available is False

    def test_auto_capot_available_false_below_nine(self) -> None:
        self.trust.value = 8
        self.trust.auto_capot_used = False
        assert self.trust.auto_capot_available is False

    def test_ai_degraded_true_at_or_below_two(self) -> None:
        self.trust.value = 2
        assert self.trust.ai_degraded is True

    def test_ai_degraded_true_at_zero(self) -> None:
        self.trust.value = 0
        assert self.trust.ai_degraded is True

    def test_ai_degraded_false_above_two(self) -> None:
        self.trust.value = 3
        assert self.trust.ai_degraded is False


# ===========================================================================
# ScoreAccumulator
# ===========================================================================


class TestScoreAccumulator:
    def setup_method(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator

        self.acc = ScoreAccumulator()

    def test_default_chips_zero(self) -> None:
        assert self.acc.chips == 0

    def test_default_mult_one(self) -> None:
        assert self.acc.mult == 1.0

    def test_total_chips_times_mult(self) -> None:
        self.acc.chips = 10
        self.acc.mult = 2.0
        assert self.acc.total == 20

    def test_total_truncates_to_int(self) -> None:
        self.acc.chips = 10
        self.acc.mult = 1.5
        assert self.acc.total == 15
        assert isinstance(self.acc.total, int)

    def test_trick_won_event_adds_card_points(self) -> None:
        evt = make_trick_event(card_points=14)
        self.acc.on_event(evt)
        assert self.acc.chips == 14

    def test_declaration_scored_adds_points(self) -> None:
        evt = make_decl_event(points=20)
        self.acc.on_event(evt)
        assert self.acc.chips == 20

    def test_attach_jokers_and_on_event_triggers_joker(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LePremierSang

        joker = LePremierSang()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.SOUTH, trick_number=1)
        self.acc.on_event(evt)
        # LePremierSang gives +2 mult on trick 1
        assert self.acc.mult == 3.0

    def test_attach_jokers_none_means_empty(self) -> None:
        self.acc.attach_jokers([])
        evt = make_trick_event(card_points=5)
        self.acc.on_event(evt)
        assert self.acc.chips == 5
        assert self.acc.mult == 1.0

    def test_popup_lines_contains_summary(self) -> None:
        self.acc.chips = 20
        self.acc.mult = 2.0
        lines = self.acc.popup_lines
        assert any("Chips" in ln and "Mult" in ln for ln in lines)

    def test_popup_lines_last_line_has_total(self) -> None:
        self.acc.chips = 10
        self.acc.mult = 3.0
        last = self.acc.popup_lines[-1]
        assert "30" in last  # 10 * 3.0 = 30

    def test_joker_add_chips_applied(self) -> None:
        from belote.belatro.items.partner_jokers.passive import LeMiroir

        joker = LeMiroir()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.NORTH)
        self.acc.on_event(evt)
        assert self.acc.chips == 5

    def test_joker_times_mult_applied(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeDernierMot

        joker = LeDernierMot()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.SOUTH, is_last=True, card_points=10)
        self.acc.on_event(evt)
        # card_points=10 added to chips, then joker gives add_chips=-10 and times_mult=2.0
        # chips = 10 + (-10) = 0, mult = 1.0 * 2.0 = 2.0
        assert self.acc.chips == 0
        assert self.acc.mult == 2.0

    def test_carnet_active_adds_mult_on_south_win(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator

        acc = ScoreAccumulator(carnet_active=True)
        evt = make_trick_event(winner=Seat.SOUTH)
        acc.on_event(evt)
        assert acc.mult == 2.0

    def test_carnet_does_not_trigger_on_north_win(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator

        acc = ScoreAccumulator(carnet_active=True)
        evt = make_trick_event(winner=Seat.NORTH)
        acc.on_event(evt)
        assert acc.mult == 1.0


# ===========================================================================
# BelAtroRun (run state)
# ===========================================================================


class TestBelAtroRun:
    def setup_method(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun

        self.run = BelAtroRun()

    def test_default_ante_is_one(self) -> None:
        assert self.run.ante_number == 1

    def test_default_blind_index_is_zero(self) -> None:
        assert self.run.blind_index == 0

    def test_default_run_over_is_false(self) -> None:
        assert self.run.run_over is False

    def test_default_run_won_is_false(self) -> None:
        assert self.run.run_won is False

    def test_default_deck_id(self) -> None:
        assert self.run.deck_id == "classique"

    def test_target_score_ante1_blind0(self) -> None:
        assert self.run.target_score == 100

    def test_current_blind_is_small_blind(self) -> None:
        assert self.run.current_blind.name == "Small Blind"

    def test_advance_blind_zero_to_one(self) -> None:
        self.run.advance_blind()
        assert self.run.blind_index == 1

    def test_advance_blind_one_to_two(self) -> None:
        self.run.blind_index = 1
        self.run.advance_blind()
        assert self.run.blind_index == 2

    def test_advance_blind_two_goes_to_next_ante(self) -> None:
        self.run.blind_index = 2
        self.run.advance_blind()
        assert self.run.ante_number == 2
        assert self.run.blind_index == 0

    def test_advance_blind_wraps_correctly_across_antes(self) -> None:
        # Advance from 1-0 through to 2-1
        self.run.advance_blind()  # → 1-1
        self.run.advance_blind()  # → 1-2
        self.run.advance_blind()  # → 2-0
        assert self.run.ante_number == 2
        assert self.run.blind_index == 0

    def test_advance_blind_ante8_boss_sets_run_won(self) -> None:
        self.run.ante_number = 8
        self.run.blind_index = 2
        self.run.advance_blind()
        assert self.run.run_won is True

    def test_run_not_won_before_final_advance(self) -> None:
        self.run.ante_number = 8
        self.run.blind_index = 1
        self.run.advance_blind()
        assert self.run.run_won is False

    def test_target_score_changes_with_blind(self) -> None:
        self.run.advance_blind()  # → big blind
        assert self.run.target_score == 150

    def test_economy_defaults(self) -> None:
        assert self.run.economy.money == 4  # classique deck starts with 4

    def test_joker_slots_default(self) -> None:
        from belote.belatro.core.run_state import MAX_JOKER_SLOTS

        assert self.run.joker_slots == MAX_JOKER_SLOTS

    def test_show_north_hand_default_false(self) -> None:
        assert self.run.show_north_hand is False


# ===========================================================================
# EventBus
# ===========================================================================


class TestEventBus:
    def setup_method(self) -> None:
        from belote.belatro.engine.event_bus import EventBus

        self.bus = EventBus()

    def test_subscribe_and_emit_calls_handler(self) -> None:
        received: list[Any] = []
        self.bus.subscribe(received.append)
        evt = make_trick_event()
        self.bus.emit(evt)
        assert received == [evt]

    def test_multiple_handlers_all_called(self) -> None:
        calls_a: list[Any] = []
        calls_b: list[Any] = []
        self.bus.subscribe(calls_a.append)
        self.bus.subscribe(calls_b.append)
        evt = make_trick_event()
        self.bus.emit(evt)
        assert calls_a == [evt]
        assert calls_b == [evt]

    def test_unsubscribe_removes_handler(self) -> None:
        calls: list[Any] = []
        self.bus.subscribe(calls.append)
        self.bus.unsubscribe(calls.append)
        self.bus.emit(make_trick_event())
        assert calls == []

    def test_emit_with_no_handlers_does_nothing(self) -> None:
        # Should not raise
        self.bus.emit(make_trick_event())

    def test_emit_passes_exact_event_object(self) -> None:
        received: list[Any] = []
        self.bus.subscribe(received.append)
        evt = make_decl_event(points=99)
        self.bus.emit(evt)
        assert received[0].points == 99

    def test_handler_receives_different_event_types(self) -> None:
        from belote.belatro.engine.event_bus import BeloteAnnouncedEvent

        received: list[Any] = []
        self.bus.subscribe(received.append)
        evt1 = make_trick_event()
        evt2 = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False)
        self.bus.emit(evt1)
        self.bus.emit(evt2)
        assert len(received) == 2


# ===========================================================================
# Trick-timing jokers
# ===========================================================================


class TestLePremierSang:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LePremierSang

        self.joker = LePremierSang()

    def test_south_wins_trick_one_returns_add_mult(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        assert result is not None
        assert result.add_mult == 2.0

    def test_south_wins_trick_two_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=2))
        assert result is None

    def test_north_wins_trick_one_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert result is None

    def test_on_round_start_resets_active_flag(self) -> None:
        # Fire it, then reset
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        assert self.joker._active is True
        self.joker.on_round_start()
        assert self.joker._active is False


class TestLeSergent:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeSergent

        self.joker = LeSergent()

    def test_south_win_returns_add_mult(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH))
        assert result is not None
        assert result.add_mult == 0.5

    def test_consecutive_south_wins_both_give_mult(self) -> None:
        r1 = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        r2 = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=2))
        assert r1.add_mult == 0.5
        assert r2.add_mult == 0.5
        assert self.joker._streak == 2

    def test_north_win_resets_streak(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=2))
        assert self.joker._streak == 0

    def test_north_win_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        assert result is None

    def test_on_round_start_resets_streak(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        self.joker.on_round_start()
        assert self.joker._streak == 0


class TestLeDernierMot:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeDernierMot

        self.joker = LeDernierMot()

    def test_south_last_trick_returns_result(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, is_last=True))
        assert result is not None
        assert result.add_chips == -10
        assert result.times_mult == 2.0

    def test_south_non_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, is_last=False))
        assert result is None

    def test_north_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, is_last=True))
        assert result is None


class TestLExecuteur:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LExecuteur

        self.joker = LExecuteur()

    def test_south_last_trick_returns_result(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, is_last=True))
        assert result is not None
        assert result.add_chips == 40
        assert result.times_mult == 1.5

    def test_south_non_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, is_last=False))
        assert result is None

    def test_north_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, is_last=True))
        assert result is None


# ===========================================================================
# Partner jokers – passive
# ===========================================================================


class TestLeMiroir:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.passive import LeMiroir

        self.joker = LeMiroir()

    def test_north_wins_gives_chips(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        assert result is not None
        assert result.add_chips == 5

    def test_south_wins_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH))
        assert result is None

    def test_east_wins_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.EAST))
        assert result is None


class TestLaSymbiose:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.passive import LaSymbiose

        self.joker = LaSymbiose()

    def test_north_declaration_gives_times_mult(self) -> None:
        evt = make_decl_event(seat=Seat.NORTH, points=20)
        result = self.joker.on_declaration(evt)
        assert result is not None
        assert result.times_mult == pytest.approx(1.2)

    def test_south_declaration_returns_none(self) -> None:
        evt = make_decl_event(seat=Seat.SOUTH, points=20)
        result = self.joker.on_declaration(evt)
        assert result is None


class TestLeRelais:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.passive import LeRelais

        self.joker = LeRelais()

    def test_north_wins_trick_one_gives_chips(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert result is not None
        assert result.add_chips == 15

    def test_north_wins_trick_two_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=2))
        assert result is None

    def test_south_wins_trick_one_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        assert result is None

    def test_does_not_double_trigger_trick_one(self) -> None:
        r1 = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        # Simulate another trick_number=1 event (shouldn't happen in real play but guard against it)
        r2 = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert r1 is not None
        assert r2 is None

    def test_round_start_resets_triggered(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert self.joker._triggered is True
        self.joker.on_round_start()
        assert self.joker._triggered is False
        # Can trigger again after reset
        r = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert r is not None


# ===========================================================================
# Partner jokers – risky
# ===========================================================================


class TestLAventurier:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.risky import LAventurier

        self.joker = LAventurier()

    def _south_win(self, n: int = 1) -> None:
        for i in range(n):
            self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=i + 1))

    def _north_win(self, n: int = 1, offset: int = 0) -> None:
        for i in range(n):
            self.joker.on_trick_won(
                make_trick_event(winner=Seat.NORTH, trick_number=i + 1 + offset)
            )

    def test_not_triggered_with_few_wins(self) -> None:
        self._south_win(2)
        self._north_win(2)
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=5))
        assert result is None

    def test_triggered_when_both_reach_three(self) -> None:
        self._south_win(2)
        self._north_win(3, offset=2)
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=6))
        assert result is not None
        assert result.times_mult == 2.0

    def test_resets_on_round_start(self) -> None:
        self._south_win(3)
        self._north_win(3)
        self.joker.on_round_start()
        assert self.joker._south_wins == 0
        assert self.joker._north_wins == 0


class TestLeMartyr:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.risky import LeMartyr

        self.joker = LeMartyr()

    def test_north_zero_wins_gives_times_mult_at_round_end(self) -> None:
        result = self.joker.on_round_end(())
        assert result is not None
        assert result.times_mult == 3.0

    def test_north_won_a_trick_gives_none_at_round_end(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        result = self.joker.on_round_end(())
        assert result is None

    def test_on_trick_won_returns_none_always(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        assert result is None

    def test_resets_on_round_start(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        self.joker.on_round_start()
        assert self.joker._north_wins == 0
        # Should give mult again since north wins reset to 0
        result = self.joker.on_round_end(())
        assert result is not None


class TestLeParasite:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.risky import LeParasite

        self.joker = LeParasite()

    def test_first_north_win_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        assert result is None

    def test_second_north_win_returns_none(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=2))
        assert result is None

    def test_third_north_win_gives_money(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=1))
        self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=2))
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=3))
        assert result is not None
        assert result.add_money == 1

    def test_south_wins_do_not_count(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1))
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=2))
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=3))
        assert result is None

    def test_resets_on_round_start(self) -> None:
        for i in range(3):
            self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=i + 1))
        self.joker.on_round_start()
        assert self.joker._north_wins == 0


# ===========================================================================
# Partner jokers – shaper
# ===========================================================================


class TestLeGenereux:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.shaper import LeGenereux

        self.joker = LeGenereux()

    def test_north_wins_gives_three_chips(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        assert result is not None
        assert result.add_chips == 3

    def test_south_wins_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH))
        assert result is None

    def test_multiple_north_wins_each_give_chips(self) -> None:
        for i in range(5):
            result = self.joker.on_trick_won(
                make_trick_event(winner=Seat.NORTH, trick_number=i + 1)
            )
            assert result is not None
            assert result.add_chips == 3


class TestLaSentinelleP:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.shaper import LaSentinelleP

        self.joker = LaSentinelleP()
        self.trump = Suit.SPADES

    def _make_trump_win(self, trick_number: int = 1) -> TrickWonEvent:
        trump_card = Card(Suit.SPADES, Rank.ACE)
        return make_trick_event(
            winner=Seat.NORTH,
            trick_number=trick_number,
            cards=(trump_card,),
            trump=self.trump,
        )

    def _make_plain_win(self, trick_number: int = 1) -> TrickWonEvent:
        plain_card = Card(Suit.HEARTS, Rank.ACE)
        return make_trick_event(
            winner=Seat.NORTH,
            trick_number=trick_number,
            cards=(plain_card,),
            trump=self.trump,
        )

    def test_round_end_with_no_trump_led_gives_mult(self) -> None:
        self.joker.on_trick_won(self._make_plain_win())
        result = self.joker.on_round_end(())
        assert result is not None
        assert result.times_mult == pytest.approx(1.5)

    def test_round_end_after_trump_led_returns_none(self) -> None:
        self.joker.on_trick_won(self._make_trump_win())
        result = self.joker.on_round_end(())
        assert result is None

    def test_on_round_start_resets_trump_led(self) -> None:
        self.joker.on_trick_won(self._make_trump_win())
        assert self.joker._trump_led is True
        self.joker.on_round_start()
        assert self.joker._trump_led is False

    def test_no_tricks_gives_mult(self) -> None:
        result = self.joker.on_round_end(())
        assert result is not None

    def test_on_trick_won_returns_none(self) -> None:
        result = self.joker.on_trick_won(self._make_plain_win())
        assert result is None


class TestLeCalculateur:
    def setup_method(self) -> None:
        from belote.belatro.items.partner_jokers.shaper import LeCalculateur

        self.joker = LeCalculateur()

    def test_north_win_gives_add_mult(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH))
        assert result is not None
        assert result.add_mult == pytest.approx(0.3)

    def test_south_win_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH))
        assert result is None

    def test_accumulates_north_win_count(self) -> None:
        for i in range(4):
            self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=i + 1))
        assert self.joker._north_wins == 4

    def test_round_start_resets_count(self) -> None:
        for i in range(3):
            self.joker.on_trick_won(make_trick_event(winner=Seat.NORTH, trick_number=i + 1))
        self.joker.on_round_start()
        assert self.joker._north_wins == 0


# ===========================================================================
# Contract & Economy & Hand-composition jokers
# ===========================================================================


class TestLIdeologue:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LIdeologue

        self.joker = LIdeologue()

    def test_south_wins_sans_atout_with_jack(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=None, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt)
        assert result is not None
        assert result.add_chips == 18

    def test_south_wins_with_trump_returns_none(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=Suit.HEARTS, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt)
        assert result is None

    def test_north_wins_returns_none(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.NORTH, trump=None, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt)
        assert result is None


class TestLePatriote:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LePatriote

        self.joker = LePatriote()

    def test_south_wins_with_trump_cards(self) -> None:
        # Jack of trump is 20 pts. 50% extra is 10.
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=Suit.HEARTS, cards=(jack_hearts,))
        result = self.joker.on_trick_won(evt)
        assert result is not None
        assert result.add_chips == 10

    def test_south_wins_no_trump_returns_none(self) -> None:
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=None, cards=(jack_hearts,))
        result = self.joker.on_trick_won(evt)
        assert result is None


class TestLePuriste:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LePuriste

        self.joker = LePuriste()

    def test_sans_atout_win_gives_money(self) -> None:
        from belote.scoring import ScoringBreakdown

        breakdown = ScoringBreakdown(
            taker_team=0,
            table_taker_pts=100,
            table_defender_pts=62,
            credit_taker_pts=100,
            credit_defender_pts=62,
            last_trick_team=0,
            taker_declarations=0,
            defender_declarations=0,
            taker_belote=0,
            defender_belote=0,
            taker_rebelote=False,
            defender_rebelote=False,
            taker_total=100,
            defender_total=62,
            is_capot=False,
            is_failed=False,
        )
        evt = make_round_end_event(breakdown=breakdown, taker_seat=Seat.SOUTH, trump=None)
        result = self.joker.on_round_end(evt)
        assert result is not None
        assert result.add_money == 10

    def test_atout_win_returns_none(self) -> None:
        from belote.scoring import ScoringBreakdown

        breakdown = ScoringBreakdown(
            taker_team=0,
            table_taker_pts=100,
            table_defender_pts=62,
            credit_taker_pts=100,
            credit_defender_pts=62,
            last_trick_team=0,
            taker_declarations=0,
            defender_declarations=0,
            taker_belote=0,
            defender_belote=0,
            taker_rebelote=False,
            defender_rebelote=False,
            taker_total=100,
            defender_total=62,
            is_capot=False,
            is_failed=False,
        )
        evt = make_round_end_event(breakdown=breakdown, taker_seat=Seat.SOUTH, trump=Suit.HEARTS)
        result = self.joker.on_round_end(evt)
        assert result is None


class TestLeBanquier:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LeBanquier

        self.joker = LeBanquier()

    def test_bonus_money_on_high_score(self) -> None:
        from belote.scoring import ScoringBreakdown

        # 110 points -> (110-80)//10 = 3
        breakdown = ScoringBreakdown(
            taker_team=0,
            table_taker_pts=110,
            table_defender_pts=52,
            credit_taker_pts=110,
            credit_defender_pts=52,
            last_trick_team=0,
            taker_declarations=0,
            defender_declarations=0,
            taker_belote=0,
            defender_belote=0,
            taker_rebelote=False,
            defender_rebelote=False,
            taker_total=110,
            defender_total=52,
            is_capot=False,
            is_failed=False,
        )
        evt = make_round_end_event(breakdown=breakdown, taker_seat=Seat.SOUTH, trump=Suit.HEARTS)
        result = self.joker.on_round_end(evt)
        assert result is not None
        assert result.add_money == 3

    def test_no_bonus_on_low_score(self) -> None:
        from belote.scoring import ScoringBreakdown

        # 85 points -> (85-80)//10 = 0
        breakdown = ScoringBreakdown(
            taker_team=0,
            table_taker_pts=85,
            table_defender_pts=77,
            credit_taker_pts=85,
            credit_defender_pts=77,
            last_trick_team=0,
            taker_declarations=0,
            defender_declarations=0,
            taker_belote=0,
            defender_belote=0,
            taker_rebelote=False,
            defender_rebelote=False,
            taker_total=85,
            defender_total=77,
            is_capot=False,
            is_failed=False,
        )
        evt = make_round_end_event(breakdown=breakdown, taker_seat=Seat.SOUTH, trump=Suit.HEARTS)
        result = self.joker.on_round_end(evt)
        assert result is None


class TestLePasseur:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LePasseur

        self.joker = LePasseur()

    def test_north_pass_gives_money(self) -> None:
        evt = make_bid_event(seat=Seat.NORTH, trump=None, contract="normal")
        result = self.joker.on_bid(evt)
        assert result is not None
        assert result.add_money == 2

    def test_north_bid_returns_none(self) -> None:
        evt = make_bid_event(seat=Seat.NORTH, trump=Suit.HEARTS, contract="normal")
        result = self.joker.on_bid(evt)
        assert result is None


class TestLeNotaire:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LeNotaire

        self.joker = LeNotaire()

    def test_south_belote_gives_money_removes_chips(self) -> None:
        evt = make_belote_event(seat=Seat.SOUTH, is_rebelote=False)
        result = self.joker.on_belote(evt)
        assert result is not None
        assert result.add_money == 5
        assert result.add_chips == -20


class TestLaSentinelle:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.hand_comp import LaSentinelle

        self.joker = LaSentinelle()

    def test_trump_jack_in_hand_gives_mult(self) -> None:
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        evt = make_round_end_event(
            breakdown=None, taker_seat=Seat.SOUTH, trump=Suit.HEARTS, hand_remainder=(jack_hearts,)
        )
        result = self.joker.on_round_end(evt)
        assert result is not None
        assert result.times_mult == 3.0

    def test_no_trump_jack_returns_none(self) -> None:
        evt = make_round_end_event(
            breakdown=None, taker_seat=Seat.SOUTH, trump=Suit.HEARTS, hand_remainder=()
        )
        result = self.joker.on_round_end(evt)
        assert result is None


class TestLeFantome:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.hand_comp import LeFantome

        self.joker = LeFantome()

    def test_cards_in_hand_give_mult(self) -> None:
        cards = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.EIGHT))
        evt = make_round_end_event(
            breakdown=None, taker_seat=Seat.SOUTH, trump=Suit.HEARTS, hand_remainder=cards
        )
        result = self.joker.on_round_end(evt)
        assert result is not None
        assert result.add_mult == 1.0  # 2 cards * 0.5


# ===========================================================================
# Profile & SaveManager
# ===========================================================================


class TestProfile:
    def setup_method(self) -> None:
        from belote.belatro.progression.save import Profile

        self.profile = Profile()

    def test_default_unlocked_ids_has_three_items(self) -> None:
        assert len(self.profile.unlocked_ids) == 3

    def test_default_unlocked_ids_contains_expected(self) -> None:
        assert "le_classique" in self.profile.unlocked_ids
        assert "le_courageux" in self.profile.unlocked_ids
        assert "l_econome" in self.profile.unlocked_ids

    def test_stats_has_four_keys(self) -> None:
        assert len(self.profile.stats) == 4

    def test_stats_all_zero(self) -> None:
        assert all(v == 0 for v in self.profile.stats.values())

    def test_stats_contains_expected_keys(self) -> None:
        for key in ("runs_won", "total_capots", "sans_atout_wins", "tout_atout_wins"):
            assert key in self.profile.stats

    def test_is_unlocked_true_for_default_item(self) -> None:
        assert self.profile.is_unlocked("le_classique") is True

    def test_is_unlocked_false_for_unknown_item(self) -> None:
        assert self.profile.is_unlocked("not_a_real_item") is False

    def test_unlock_new_item_returns_true(self) -> None:
        result = self.profile.unlock("brand_new_item")
        assert result is True

    def test_unlock_new_item_adds_to_list(self) -> None:
        self.profile.unlock("brand_new_item")
        assert "brand_new_item" in self.profile.unlocked_ids

    def test_unlock_duplicate_returns_false(self) -> None:
        result = self.profile.unlock("le_classique")
        assert result is False

    def test_unlock_duplicate_does_not_add_again(self) -> None:
        original_count = len(self.profile.unlocked_ids)
        self.profile.unlock("le_classique")
        assert len(self.profile.unlocked_ids) == original_count


class TestSaveManager:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from belote.belatro.progression.save import Profile, SaveManager

        original_env = os.environ.get("XDG_DATA_HOME")
        try:
            os.environ["XDG_DATA_HOME"] = str(tmp_path)
            sm = SaveManager("belatro_test")
            profile = Profile()
            profile.unlock("test_item_xyz")
            profile.stats["runs_won"] = 3
            sm.save_profile(profile)

            loaded = sm.load_profile()
            assert "test_item_xyz" in loaded.unlocked_ids
            assert loaded.stats["runs_won"] == 3
        finally:
            if original_env is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = original_env

    def test_load_returns_default_profile_when_no_file(self, tmp_path: Path) -> None:
        from belote.belatro.progression.save import Profile, SaveManager

        original_env = os.environ.get("XDG_DATA_HOME")
        try:
            os.environ["XDG_DATA_HOME"] = str(tmp_path)
            sm = SaveManager("belatro_no_file_test")
            loaded = sm.load_profile()
            assert isinstance(loaded, Profile)
            assert len(loaded.unlocked_ids) == 3
        finally:
            if original_env is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = original_env

    def test_roundtrip_preserves_all_defaults(self, tmp_path: Path) -> None:
        from belote.belatro.progression.save import Profile, SaveManager

        original_env = os.environ.get("XDG_DATA_HOME")
        try:
            os.environ["XDG_DATA_HOME"] = str(tmp_path)
            sm = SaveManager("belatro_defaults_test")
            profile = Profile()
            sm.save_profile(profile)
            loaded = sm.load_profile()
            assert sorted(loaded.unlocked_ids) == sorted(profile.unlocked_ids)
            assert loaded.stats == profile.stats
        finally:
            if original_env is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = original_env


# ===========================================================================
# Ante table
# ===========================================================================


class TestAnteTable:
    def setup_method(self) -> None:
        from belote.belatro.run.ante import ANTE_TABLE, calculate_target

        self.ANTE_TABLE = ANTE_TABLE
        self.calculate_target = calculate_target

    def test_table_has_eight_antes(self) -> None:
        assert len(self.ANTE_TABLE) == 8

    def test_each_ante_has_three_blinds(self) -> None:
        for row in self.ANTE_TABLE:
            assert len(row) == 3

    def test_first_blind_is_small(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[0].name == "Small Blind"

    def test_second_blind_is_big(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[1].name == "Big Blind"

    def test_third_blind_is_boss(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[2].name == "Boss Blind"

    def test_targets_increase_across_antes(self) -> None:
        for i in range(len(self.ANTE_TABLE) - 1):
            assert self.ANTE_TABLE[i][0].target < self.ANTE_TABLE[i + 1][0].target

    def test_within_ante_targets_increase_with_blind(self) -> None:
        for row in self.ANTE_TABLE:
            assert row[0].target < row[1].target < row[2].target

    def test_ante1_small_target_is_100(self) -> None:
        assert self.ANTE_TABLE[0][0].target == 100

    def test_ante1_big_target_is_150(self) -> None:
        assert self.ANTE_TABLE[0][1].target == 150

    def test_ante1_boss_target_is_200(self) -> None:
        assert self.ANTE_TABLE[0][2].target == 200

    def test_calculate_target_ante1_small(self) -> None:
        assert self.calculate_target(1, 0) == 100

    def test_calculate_target_ante1_big(self) -> None:
        assert self.calculate_target(1, 1) == 150

    def test_calculate_target_ante1_boss(self) -> None:
        assert self.calculate_target(1, 2) == 200

    def test_calculate_target_scales_with_ante(self) -> None:
        target_a1 = self.calculate_target(1, 0)
        target_a2 = self.calculate_target(2, 0)
        # Ante 2 should be 1.5x ante 1
        assert target_a2 == pytest.approx(target_a1 * 1.5, abs=1)

    def test_ante_numbers_are_correct(self) -> None:
        for i, row in enumerate(self.ANTE_TABLE):
            for blind in row:
                assert blind.number == i + 1


# ===========================================================================
# Boss modifiers
# ===========================================================================


class TestBossModifiers:
    def setup_method(self) -> None:
        from belote.belatro.engine.modifier_patch import PatchedGameState
        from belote.belatro.run.boss import ALL_BOSS_MODIFIERS
        from belote.game import GameState

        self.ALL_BOSS_MODIFIERS = ALL_BOSS_MODIFIERS
        hands = ((), (), (), ())
        self.gs = GameState(hands=hands)
        self.PatchedGameState = PatchedGameState

    def test_all_boss_modifiers_is_nonempty(self) -> None:
        assert len(self.ALL_BOSS_MODIFIERS) > 0

    def test_each_boss_has_id(self) -> None:
        for cls in self.ALL_BOSS_MODIFIERS:
            assert hasattr(cls, "id")
            assert isinstance(cls.id, str)
            assert len(cls.id) > 0

    def test_each_boss_has_name(self) -> None:
        for cls in self.ALL_BOSS_MODIFIERS:
            assert hasattr(cls, "name")
            assert isinstance(cls.name, str)

    def test_each_boss_has_description(self) -> None:
        for cls in self.ALL_BOSS_MODIFIERS:
            assert hasattr(cls, "description")
            assert isinstance(cls.description, str)

    def test_each_boss_apply_returns_patched_game_state(self) -> None:
        from belote.belatro.engine.modifier_patch import PatchedGameState

        for cls in self.ALL_BOSS_MODIFIERS:
            pgs = self.PatchedGameState(self.gs)
            result = cls().apply(pgs)
            assert isinstance(result, PatchedGameState)

    def test_la_grande_muette_patches_no_belote(self) -> None:
        from belote.belatro.run.boss import LaGrandeMuette

        pgs = self.PatchedGameState(self.gs)
        LaGrandeMuette().apply(pgs)
        assert pgs._no_belote is True

    def test_le_roi_mort_patches_kings_zero(self) -> None:
        from belote.belatro.run.boss import LeRoiMort

        pgs = self.PatchedGameState(self.gs)
        LeRoiMort().apply(pgs)
        assert pgs._kings_zero is True

    def test_l_anarchie_patches_dynamic_trump(self) -> None:
        from belote.belatro.run.boss import LAnarchie

        pgs = self.PatchedGameState(self.gs)
        LAnarchie().apply(pgs)
        assert pgs._dynamic_trump is True

    def test_all_boss_ids_are_unique(self) -> None:
        ids = [cls.id for cls in self.ALL_BOSS_MODIFIERS]
        assert len(ids) == len(set(ids))


# ===========================================================================
# Item Registry
# ===========================================================================


class TestItemRegistry:
    def setup_method(self) -> None:
        from belote.belatro.items.registry import ItemRegistry, register_all_items

        # Use a fresh registry to avoid state leakage
        self.registry = ItemRegistry()
        # Monkey-patch the global for register_all_items
        import belote.belatro.items.registry as reg_mod

        self._orig_registry = reg_mod.registry
        reg_mod.registry = self.registry
        register_all_items()
        reg_mod.registry = self._orig_registry

    def test_jokers_nonempty_after_registration(self) -> None:
        assert len(self.registry.jokers) > 0

    def test_planets_nonempty_after_registration(self) -> None:
        assert len(self.registry.planets) > 0

    def test_tarots_nonempty_after_registration(self) -> None:
        assert len(self.registry.tarots) > 0

    def test_vouchers_nonempty_after_registration(self) -> None:
        assert len(self.registry.vouchers) > 0

    def test_get_joker_returns_class(self) -> None:
        first_id = next(iter(self.registry.jokers))
        cls = self.registry.get_joker(first_id)
        assert cls is not None

    def test_get_joker_unknown_returns_none(self) -> None:
        assert self.registry.get_joker("not_a_real_joker_id") is None

    def test_get_planet_returns_class(self) -> None:
        first_id = next(iter(self.registry.planets))
        cls = self.registry.get_planet(first_id)
        assert cls is not None

    def test_get_tarot_returns_class(self) -> None:
        first_id = next(iter(self.registry.tarots))
        cls = self.registry.get_tarot(first_id)
        assert cls is not None

    def test_get_voucher_returns_class(self) -> None:
        first_id = next(iter(self.registry.vouchers))
        cls = self.registry.get_voucher(first_id)
        assert cls is not None

    def test_le_premier_sang_registered(self) -> None:
        assert "le_premier_sang" in self.registry.jokers

    def test_le_miroir_registered(self) -> None:
        assert "le_miroir" in self.registry.jokers

    def test_get_available_jokers_excludes_locked(self) -> None:
        from belote.belatro.progression.save import Profile

        profile = Profile()
        available = self.registry.get_available_jokers(profile)
        # All non-unlockable jokers should be available
        for jid, jcls in available.items():
            assert not getattr(jcls, "is_unlockable", False) or profile.is_unlocked(jid)


# ===========================================================================
# Shop
# ===========================================================================


class TestShop:
    def setup_method(self) -> None:
        from belote.belatro.core.run_state import BelAtroRun
        from belote.belatro.items.registry import register_all_items
        from belote.belatro.progression.save import Profile
        from belote.belatro.run.shop import Shop

        register_all_items()
        self.run = BelAtroRun()
        self.run.economy.money = 100
        self.profile = Profile()
        self.shop = Shop(self.run, self.profile)
        self.shop.generate_inventory()

    def test_generate_inventory_produces_items(self) -> None:
        assert len(self.shop.inventory) > 0

    def test_buy_item_valid_index_returns_true(self) -> None:
        item = self.shop.inventory[0]
        self.run.economy.money = item.cost + 10
        result = self.shop.buy_item(0)
        assert result is True

    def test_buy_item_removes_item_from_inventory(self) -> None:
        original_count = len(self.shop.inventory)
        self.run.economy.money = 9999
        self.shop.buy_item(0)
        assert len(self.shop.inventory) == original_count - 1

    def test_buy_item_spends_money(self) -> None:
        item = self.shop.inventory[0]
        self.run.economy.money = 999
        before = self.run.economy.money
        self.shop.buy_item(0)
        assert self.run.economy.money == before - item.cost

    def test_buy_item_insufficient_funds_returns_false(self) -> None:
        self.run.economy.money = 0
        result = self.shop.buy_item(0)
        assert result is False

    def test_buy_item_insufficient_funds_does_not_remove(self) -> None:
        original_count = len(self.shop.inventory)
        self.run.economy.money = 0
        self.shop.buy_item(0)
        assert len(self.shop.inventory) == original_count

    def test_buy_item_out_of_range_returns_false(self) -> None:
        result = self.shop.buy_item(999)
        assert result is False

    def test_buy_item_negative_index_returns_false(self) -> None:
        result = self.shop.buy_item(-1)
        assert result is False

    def test_reroll_returns_true_with_sufficient_funds(self) -> None:
        self.run.economy.money = 100
        result = self.shop.reroll()
        assert result is True

    def test_reroll_spends_money(self) -> None:
        self.run.economy.money = 100
        before = self.run.economy.money
        cost = self.shop.reroll_cost
        self.shop.reroll()
        assert self.run.economy.money == before - cost

    def test_reroll_increases_reroll_cost(self) -> None:
        self.run.economy.money = 100
        original_cost = self.shop.reroll_cost
        self.shop.reroll()
        assert self.shop.reroll_cost == original_cost + 1

    def test_reroll_regenerates_inventory(self) -> None:
        self.run.economy.money = 100
        # Reroll multiple times to reduce chance of same inventory
        for _ in range(3):
            if self.run.economy.money >= self.shop.reroll_cost:
                self.shop.reroll()
        second_types = [type(i).__name__ for i in self.shop.inventory]
        # We just check inventory was repopulated (non-empty)
        assert len(second_types) > 0

    def test_reroll_fails_with_no_money(self) -> None:
        self.run.economy.money = 0
        result = self.shop.reroll()
        assert result is False

    def test_buying_joker_adds_to_run_jokers(self) -> None:
        from belote.belatro.items.base import Joker

        # Find a joker in inventory
        for i, item in enumerate(self.shop.inventory):
            if isinstance(item, Joker):
                self.run.economy.money = 9999
                before = len(self.run.jokers)
                self.shop.buy_item(i)
                assert len(self.run.jokers) == before + 1
                break

    def test_buying_voucher_adds_to_run_vouchers(self) -> None:
        from belote.belatro.items.base import Voucher

        # Find a voucher in inventory
        for i, item in enumerate(self.shop.inventory):
            if isinstance(item, Voucher):
                self.run.economy.money = 9999
                before = len(self.run.vouchers)
                self.shop.buy_item(i)
                assert len(self.run.vouchers) == before + 1
                break
