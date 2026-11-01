"""Per-joker unit tests (trick timing, contract, economy, hand)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from belote.deck import Card, Rank, Suit
from belote.game import Seat

if TYPE_CHECKING:
    pass
from tests.belatro._events import (
    make_belote_event,
    make_bid_event,
    make_round_end_event,
    make_trick_event,
)


class TestLePremierSang:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LePremierSang

        self.joker = LePremierSang()
        self.state: dict[str, Any] = {}

    def test_south_wins_trick_one_returns_add_mult(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state
        )
        assert result is not None
        assert result.add_mult == 2.0

    def test_south_wins_trick_two_returns_none(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, trick_number=2), self.state
        )
        assert result is None

    def test_north_wins_trick_one_returns_add_mult(self) -> None:
        # 3.4.2 (H1): LePremierSang gates on team_of(winner)==0 — partner
        # (North) winning trick 1 arms the joker and fires +2 mult.
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.NORTH, trick_number=1), self.state
        )
        assert result is not None
        assert result.add_mult == 2.0

    def test_east_wins_trick_one_returns_none(self) -> None:
        # Opposing team winning trick 1 must NOT arm or fire the joker.
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.EAST, trick_number=1), self.state
        )
        assert result is None
        assert self.state.get(f"{self.joker.id}_active") is not True

    def test_on_round_start_resets_active_flag(self) -> None:
        # Fire it, then reset
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state)
        assert self.state.get(f"{self.joker.id}_active") is True
        self.joker.on_round_start(self.state)
        assert self.state.get(f"{self.joker.id}_active") is False


class TestLeSergent:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeSergent

        self.joker = LeSergent()
        self.state: dict[str, Any] = {}

    def test_south_win_returns_add_mult(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH), self.state)
        assert result is not None
        assert result.add_mult == 0.5

    def test_consecutive_south_wins_grow_with_streak(self) -> None:
        r1 = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state
        )
        r2 = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, trick_number=2), self.state
        )
        assert r1.add_mult == 0.5
        assert r2.add_mult == 1.0
        assert self.state.get(f"{self.joker.id}_streak") == 2

    def test_streak_bonus_caps_at_two(self) -> None:
        mults = [
            self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=i), self.state)
            for i in range(1, 9)
        ]
        assert [r.add_mult for r in mults if r] == [0.5, 1.0, 1.5, 2.0, 2.0, 2.0, 2.0, 2.0]

    def test_loss_restarts_streak_bonus(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state)
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=2), self.state)
        self.joker.on_trick_won(make_trick_event(winner=Seat.EAST, trick_number=3), self.state)
        r = self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=4), self.state)
        assert r is not None and r.add_mult == 0.5

    def test_east_win_resets_streak(self) -> None:
        # 3.4.2 (H1): an opposing-team trick (East/West) now resets the
        # streak; partner (North) wins continue the streak instead.
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state)
        self.joker.on_trick_won(make_trick_event(winner=Seat.EAST, trick_number=2), self.state)
        assert self.state.get(f"{self.joker.id}_streak") == 0

    def test_north_win_continues_streak(self) -> None:
        # H1: partner (North) is on team NS — joker fires and extends streak.
        r1 = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state
        )
        r2 = self.joker.on_trick_won(
            make_trick_event(winner=Seat.NORTH, trick_number=2), self.state
        )
        assert r1 is not None and r1.add_mult == 0.5
        assert r2 is not None and r2.add_mult == 1.0
        assert self.state.get(f"{self.joker.id}_streak") == 2

    def test_east_win_returns_none(self) -> None:
        result = self.joker.on_trick_won(make_trick_event(winner=Seat.EAST), self.state)
        assert result is None

    def test_on_round_start_resets_streak(self) -> None:
        self.joker.on_trick_won(make_trick_event(winner=Seat.SOUTH, trick_number=1), self.state)
        self.joker.on_round_start(self.state)
        assert self.state.get(f"{self.joker.id}_streak") == 0


class TestLeDernierMot:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LeDernierMot

        self.joker = LeDernierMot()
        self.state: dict[str, Any] = {}

    def test_south_last_trick_returns_result(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, is_last=True), self.state
        )
        assert result is not None
        assert result.add_chips == -10
        assert result.times_mult == 2.0

    def test_south_non_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, is_last=False), self.state
        )
        assert result is None

    def test_north_last_trick_returns_result(self) -> None:
        # 3.2.0: LeDernierMot now keys on team (NS), not seat (SOUTH) — the
        # Dix de Der goes to whoever wins the LAST trick, regardless of who
        # personally took it, so the joker must fire when North wins it too.
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.NORTH, is_last=True), self.state
        )
        assert result is not None
        assert result.add_chips == -10
        assert result.times_mult == 2.0

    def test_east_last_trick_returns_none(self) -> None:
        # EW team winning the last trick must NOT fire LeDernierMot.
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.EAST, is_last=True), self.state
        )
        assert result is None


class TestLExecuteur:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.trick_timing import LExecuteur

        self.joker = LExecuteur()
        self.state: dict[str, Any] = {}

    def test_south_last_trick_returns_result(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, is_last=True), self.state
        )
        assert result is not None
        assert result.add_chips == 40
        assert result.times_mult == 1.5

    def test_south_non_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.SOUTH, is_last=False), self.state
        )
        assert result is None

    def test_north_last_trick_returns_result(self) -> None:
        # 3.4.2 (H1): partner (North) taking the last trick now fires
        # L'Exécuteur — it gates on team_of(winner)==0, not seat==SOUTH.
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.NORTH, is_last=True), self.state
        )
        assert result is not None
        assert result.add_chips == 40
        assert result.times_mult == 1.5

    def test_east_last_trick_returns_none(self) -> None:
        result = self.joker.on_trick_won(
            make_trick_event(winner=Seat.EAST, is_last=True), self.state
        )
        assert result is None


class TestLIdeologue:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LIdeologue

        self.joker = LIdeologue()
        self.state: dict[str, Any] = {}

    def test_south_wins_sans_atout_with_jack(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=None, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is not None
        assert result.add_chips == 18

    def test_south_wins_with_trump_returns_none(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=Suit.HEARTS, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is None

    def test_north_wins_sans_atout_returns_result(self) -> None:
        # 3.4.2 (H1): partner (North) winning a Sans Atout trick containing
        # a Jack now fires LIdeologue.
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.NORTH, trump=None, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is not None
        assert result.add_chips == 18

    def test_east_wins_returns_none(self) -> None:
        jack_spades = Card(Suit.SPADES, Rank.JACK)
        evt = make_trick_event(winner=Seat.EAST, trump=None, cards=(jack_spades,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is None


class TestLePatriote:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LePatriote

        self.joker = LePatriote()
        self.state: dict[str, Any] = {}

    def test_south_wins_with_trump_cards(self) -> None:
        # Jack of trump is 20 pts. 50% extra is 10.
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=Suit.HEARTS, cards=(jack_hearts,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is not None
        assert result.add_chips == 10

    def test_south_wins_no_trump_returns_none(self) -> None:
        jack_hearts = Card(Suit.HEARTS, Rank.JACK)
        evt = make_trick_event(winner=Seat.SOUTH, trump=None, cards=(jack_hearts,))
        result = self.joker.on_trick_won(evt, self.state)
        assert result is None


class TestLePuriste:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.contract import LePuriste

        self.joker = LePuriste()
        self.state: dict[str, Any] = {}

    def test_sans_atout_win_sets_flag(self) -> None:
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
        result = self.joker.on_round_end(evt, self.state)
        assert result is None
        assert self.state.get("puriste_triggered") is True

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
        result = self.joker.on_round_end(evt, self.state)
        assert result is None


class TestLeBanquier:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LeBanquier

        self.joker = LeBanquier()
        self.state: dict[str, Any] = {}

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
        result = self.joker.on_round_end(evt, self.state)
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
        result = self.joker.on_round_end(evt, self.state)
        assert result is None


class TestLePasseur:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LePasseur

        self.joker = LePasseur()
        self.state: dict[str, Any] = {}

    def test_north_pass_gives_money(self) -> None:
        evt = make_bid_event(seat=Seat.NORTH, trump=None, contract="normal")
        result = self.joker.on_bid(evt, self.state)
        assert result is not None
        assert result.add_money == 2

    def test_north_bid_returns_none(self) -> None:
        evt = make_bid_event(seat=Seat.NORTH, trump=Suit.HEARTS, contract="normal")
        result = self.joker.on_bid(evt, self.state)
        assert result is None


class TestLeNotaire:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.economy import LeNotaire

        self.joker = LeNotaire()
        self.state: dict[str, Any] = {}

    def test_south_belote_gives_money_removes_chips(self) -> None:
        evt = make_belote_event(seat=Seat.SOUTH, is_rebelote=True)
        result = self.joker.on_belote(evt, self.state)
        assert result is not None
        assert result.add_money == 5
        assert result.add_chips == -20


class TestLaSentinelle:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.hand_comp import LaSentinelle

        self.joker = LaSentinelle()
        self.state: dict[str, Any] = {}

    # (The "Jack held but unused → ×3" payout is pinned by
    # test_joker_contracts.py::test_la_sentinelle_pays_when_jack_held_but_unused.)

    def test_no_trump_jack_returns_none(self) -> None:
        self.state["la_sentinelle_had_jack"] = False
        evt = make_round_end_event(
            breakdown=None, taker_seat=Seat.SOUTH, trump=Suit.HEARTS, hand_remainder=()
        )
        result = self.joker.on_round_end(evt, self.state)
        assert result is None


class TestLeFantome:
    def setup_method(self) -> None:
        from belote.belatro.items.jokers.hand_comp import LeFantome

        self.joker = LeFantome()
        self.state: dict[str, Any] = {}

    def test_cards_in_hand_give_mult(self) -> None:
        cards = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.EIGHT))
        evt = make_round_end_event(
            breakdown=None, taker_seat=Seat.SOUTH, trump=Suit.HEARTS, hand_remainder=cards
        )
        result = self.joker.on_round_end(evt, self.state)
        assert result is not None
        assert result.add_mult == 1.0  # 2 cards * 0.5


class TestLAccumulateurTeamCredit:
    """3.7.1 BA-L2: L'Accumulateur credits any NS trick win, not just South.

    Pre-3.7.1 the joker gated on `event.winner == Seat.SOUTH`, silently
    dropping +5 chips per 7/8 whenever the partner (North) won the trick.
    The description says "you win in a trick" — in BelAtro "you" = team
    (NS), same convention as Le Patriote / Le Premier Sang fixed in 3.5.0.
    """

    def setup_method(self) -> None:
        from belote.belatro.items.jokers.hand_comp import LAccumulateur

        self.joker = LAccumulateur()
        self.state: dict = {}
        self.joker.on_round_start(self.state)

    def _trick_with_seven(self, winner: Seat) -> object:
        return make_trick_event(
            winner=winner,
            cards=(
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.HEARTS, Rank.NINE),
                Card(Suit.HEARTS, Rank.KING),
                Card(Suit.HEARTS, Rank.ACE),
            ),
            trump=Suit.HEARTS,
        )

    def test_south_win_credits(self) -> None:
        self.joker.on_trick_won(self._trick_with_seven(Seat.SOUTH), self.state)
        assert self.state["laccumulateur_stored_chips"] == 5

    def test_north_partner_win_credits(self) -> None:
        """Partner (NORTH) trick wins must credit — the BA-L2 fix."""
        self.joker.on_trick_won(self._trick_with_seven(Seat.NORTH), self.state)
        assert self.state["laccumulateur_stored_chips"] == 5

    def test_east_win_does_not_credit(self) -> None:
        self.joker.on_trick_won(self._trick_with_seven(Seat.EAST), self.state)
        assert self.state["laccumulateur_stored_chips"] == 0

    def test_west_win_does_not_credit(self) -> None:
        self.joker.on_trick_won(self._trick_with_seven(Seat.WEST), self.state)
        assert self.state["laccumulateur_stored_chips"] == 0

    def test_mixed_round_credits_only_ns_tricks(self) -> None:
        """Realistic round: NS and EW trade tricks; only NS counts."""
        self.joker.on_trick_won(self._trick_with_seven(Seat.SOUTH), self.state)  # +5
        self.joker.on_trick_won(self._trick_with_seven(Seat.EAST), self.state)  # +0
        self.joker.on_trick_won(self._trick_with_seven(Seat.NORTH), self.state)  # +5
        self.joker.on_trick_won(self._trick_with_seven(Seat.WEST), self.state)  # +0
        assert self.state["laccumulateur_stored_chips"] == 10

    def test_credits_eight_too_not_just_seven(self) -> None:
        """Description: 'every 7 OR 8 you win' — both ranks count."""
        from belote.belatro.engine.event_bus import TrickWonEvent

        evt = TrickWonEvent(
            winner=Seat.NORTH,
            cards=(
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.HEARTS, Rank.EIGHT),
                Card(Suit.SPADES, Rank.KING),
                Card(Suit.DIAMONDS, Rank.ACE),
            ),
            trick_number=1,
            is_last=False,
            card_points=0,
            trump=Suit.HEARTS,
        )
        self.joker.on_trick_won(evt, self.state)
        assert self.state["laccumulateur_stored_chips"] == 10
