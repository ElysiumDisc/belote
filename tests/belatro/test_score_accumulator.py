"""ScoreAccumulator: chips × mult bookkeeping."""

from __future__ import annotations

from typing import TYPE_CHECKING

from belote.belatro.core.state import as_belatro
from belote.game import Seat

if TYPE_CHECKING:
    pass
from tests.belatro._events import (
    make_decl_event,
    make_trick_event,
)


class TestScoreAccumulator:
    def setup_method(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator
        from belote.game import new_game

        self.acc = ScoreAccumulator()
        self.state = as_belatro(new_game())

    def test_default_chips_zero(self) -> None:
        assert self.state._chips == 0

    def test_default_mult_one(self) -> None:
        assert self.state._mult == 1.0

    def test_total_chips_times_mult(self) -> None:
        from dataclasses import replace

        state = replace(self.state, _chips=10, _mult=2.0)
        assert self.acc.get_total(state) == 20

    def test_total_truncates_to_int(self) -> None:
        from dataclasses import replace

        state = replace(self.state, _chips=10, _mult=1.5)
        assert self.acc.get_total(state) == 15
        assert isinstance(self.acc.get_total(state), int)

    def test_trick_won_event_adds_card_points(self) -> None:
        evt = make_trick_event(card_points=14)
        state = self.acc.update_state(self.state, evt)
        assert state._chips == 14

    def test_declaration_scored_adds_points(self) -> None:
        evt = make_decl_event(points=20)
        state = self.acc.update_state(self.state, evt)
        assert state._chips == 20

    def test_attach_jokers_and_on_event_triggers_joker(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LePremierSang

        joker = LePremierSang()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.SOUTH, trick_number=1)
        state = self.acc.update_state(self.state, evt)
        # LePremierSang gives +2 mult on trick 1
        assert state._mult == 3.0

    def test_attach_jokers_none_means_empty(self) -> None:
        self.acc.attach_jokers([])
        evt = make_trick_event(card_points=5)
        state = self.acc.update_state(self.state, evt)
        assert state._chips == 5
        assert state._mult == 1.0

    def test_popup_lines_contains_summary(self) -> None:
        from dataclasses import replace

        state = replace(self.state, _chips=20, _mult=2.0)
        lines = self.acc.get_popup_lines(state)
        assert any("Chips" in ln and "Mult" in ln for ln in lines)

    def test_popup_lines_last_line_has_total(self) -> None:
        from dataclasses import replace

        state = replace(self.state, _chips=10, _mult=3.0)
        last = self.acc.get_popup_lines(state)[-1]
        assert "30" in last  # 10 * 3.0 = 30

    def test_joker_add_chips_applied(self) -> None:
        from belote.belatro.items.partner_jokers.passive import LeMiroir

        joker = LeMiroir()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.NORTH)
        state = self.acc.update_state(self.state, evt)
        assert state._chips == 5

    def test_joker_times_mult_applied(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeDernierMot

        joker = LeDernierMot()
        self.acc.attach_jokers([joker])
        evt = make_trick_event(winner=Seat.SOUTH, is_last=True, card_points=10)
        state = self.acc.update_state(self.state, evt)
        # card_points=10 added to chips, then joker gives add_chips=-10 and times_mult=2.0
        # chips = 10 + (-10) = 0, mult = 1.0 * 2.0 = 2.0
        assert state._chips == 0
        assert state._mult == 2.0

    def test_carnet_active_adds_mult_on_south_win(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator

        acc = ScoreAccumulator(carnet_active=True)
        evt = make_trick_event(winner=Seat.SOUTH)
        state = acc.update_state(self.state, evt)
        assert state._mult == 2.0

    def test_carnet_does_not_trigger_on_north_win(self) -> None:
        from belote.belatro.core.scoring import ScoreAccumulator

        acc = ScoreAccumulator(carnet_active=True)
        evt = make_trick_event(winner=Seat.NORTH)
        state = acc.update_state(self.state, evt)
        assert state._mult == 1.0
