"""4.9.7 design-call fixes: Le Diable, partner void info."""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.state import BelatroState
from belote.belatro.engine.round_driver import _diable_overcut
from belote.belatro.items.base import Joker
from belote.belatro.run.shop import Shop
from belote.belatro.ui.trust_bar import _void_label
from belote.deck import Card, Contract, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard

H, S, D = Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS


def _north_to_play(
    north: tuple[Card, ...],
    trick: tuple[TrickCard, ...],
    trump: Suit | None = H,
    contract: str = Contract.NORMAL,
) -> GameState:
    return BelatroState(
        hands=((), (), north, ()),
        turn=Seat.NORTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract=contract,
        taker=Seat.SOUTH,
        current_trick=trick,
    )


# South leads A♠ (winning), East follows 7♠; North is void in spades.
_SOUTH_WINNING = (TrickCard(Seat.SOUTH, Card(S, Rank.ACE)), TrickCard(Seat.EAST, Card(S, Rank.SEVEN)))


def test_diable_overcuts_partner_with_lowest_winning_trump() -> None:
    north = (Card(H, Rank.JACK), Card(H, Rank.EIGHT), Card(D, Rank.KING))
    assert _diable_overcut(_north_to_play(north, _SOUTH_WINNING)) == Card(H, Rank.EIGHT)


def test_diable_keeps_ai_choice_when_no_trump() -> None:
    north = (Card(D, Rank.KING), Card(D, Rank.SEVEN))
    assert _diable_overcut(_north_to_play(north, _SOUTH_WINNING)) is None


def test_diable_keeps_ai_choice_when_leading_or_sans_atout() -> None:
    north = (Card(H, Rank.JACK), Card(D, Rank.KING))
    assert _diable_overcut(_north_to_play(north, ())) is None
    sa = _north_to_play(north, _SOUTH_WINNING, trump=None, contract=Contract.SANS_ATOUT)
    assert _diable_overcut(sa) is None


def test_diable_only_picks_trumps_that_beat_the_trick() -> None:
    # East over-trumped with 9♥; only North's J♥ beats it.
    trick = (TrickCard(Seat.SOUTH, Card(S, Rank.ACE)), TrickCard(Seat.EAST, Card(H, Rank.NINE)))
    north = (Card(H, Rank.SEVEN), Card(H, Rank.JACK), Card(D, Rank.KING))
    assert _diable_overcut(_north_to_play(north, trick)) == Card(H, Rank.JACK)


def test_void_label_lists_north_empty_suits_during_play() -> None:
    state = _north_to_play((Card(H, Rank.JACK), Card(D, Rank.KING)), ())
    assert _void_label(state) == f"Void: {S.symbol}{Suit.CLUBS.symbol}"


def test_void_label_generic_outside_play() -> None:
    assert _void_label(None) == "Void Info"
    bidding = BelatroState(hands=((), (), (Card(H, Rank.JACK),), ()), phase=Phase.BIDDING)
    assert _void_label(bidding) == "Void Info"


# ── Selling jokers (shop) ─────────────────────────────────────────────


def _shop_with(*jokers: Joker) -> Shop:
    run = BelAtroRun()
    run.jokers.extend(jokers)
    return Shop(run)


def test_sell_joker_pays_half_cost_and_frees_slot() -> None:
    from belote.belatro.items.jokers.trick_timing import LeSergent

    shop = _shop_with(LeSergent())
    money = shop.run.economy.money
    assert shop.sell_joker(0) == LeSergent.cost // 2
    assert shop.run.economy.money == money + LeSergent.cost // 2
    assert shop.run.jokers == []


def test_corrupted_joker_cannot_be_sold() -> None:
    from belote.belatro.items.jokers.corrupted import LeTraitre

    shop = _shop_with(LeTraitre())
    assert not shop.can_sell(0)
    assert shop.sell_joker(0) == 0
    assert len(shop.run.jokers) == 1


def test_selling_negative_joker_returns_its_extra_slot() -> None:
    from belote.belatro.items.base import Edition
    from belote.belatro.items.jokers.trick_timing import LeSergent

    neg = LeSergent()
    neg.edition = Edition.NEGATIVE
    shop = _shop_with(neg)
    shop.run.joker_slots += 1  # as buy_item does
    slots = shop.run.joker_slots
    shop.sell_joker(0)
    assert shop.run.joker_slots == slots - 1


def test_sell_out_of_range_is_refused() -> None:
    shop = _shop_with()
    assert shop.sell_joker(0) == 0
