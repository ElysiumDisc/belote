"""Phase 1 plumbing tests: TOUT_ATOUT, coinche level on events, Rarity enum,
new BelAtroRun fields, BeloteAnnouncedEvent emission."""

from __future__ import annotations

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.engine.event_bus import BidMadeEvent, RoundEndEvent
from belote.belatro.items.base import Joker, Planet, Rarity, Tarot, Voucher
from belote.deck import CARD_SUITS, Card, Rank, Suit, card_points, make_deck, trick_rank
from belote.game import Seat

# ── Suit.TOUT_ATOUT ────────────────────────────────────────────────────────


def test_tout_atout_is_a_suit_value_not_a_card_suit() -> None:
    assert Suit.TOUT_ATOUT in list(Suit)
    assert Suit.TOUT_ATOUT.is_card_suit is False
    for s in CARD_SUITS:
        assert s.is_card_suit is True


def test_make_deck_excludes_tout_atout() -> None:
    deck = make_deck()
    assert len(deck) == 32
    assert all(c.suit.is_card_suit for c in deck)
    assert all(c.suit != Suit.TOUT_ATOUT for c in deck)


def test_card_points_under_tout_atout_uses_trump_scale() -> None:
    # Under Tout Atout, every Jack is worth 20 (not 2), every 9 is 14, etc.
    assert card_points(Card(Suit.HEARTS, Rank.JACK), Suit.TOUT_ATOUT) == 20
    assert card_points(Card(Suit.SPADES, Rank.JACK), Suit.TOUT_ATOUT) == 20
    assert card_points(Card(Suit.CLUBS, Rank.NINE), Suit.TOUT_ATOUT) == 14
    # Non-trump-suit Ace would be 11 in normal contracts; in Tout Atout it's still 11
    # (trump Ace is also 11, so the value coincidentally matches).
    assert card_points(Card(Suit.DIAMONDS, Rank.ACE), Suit.TOUT_ATOUT) == 11


def test_trick_rank_under_tout_atout_treats_all_suits_as_trump() -> None:
    # Under Tout Atout, a Hearts JACK and a Spades JACK both rank 8 + JACK_TRUMP_ORDER.
    rh = trick_rank(Card(Suit.HEARTS, Rank.JACK), Suit.TOUT_ATOUT)
    rs = trick_rank(Card(Suit.SPADES, Rank.JACK), Suit.TOUT_ATOUT)
    assert rh == rs and rh >= 8


# ── Rarity enum ────────────────────────────────────────────────────────────


def test_rarity_enum_values() -> None:
    assert Rarity.COMMON.value == "common"
    assert Rarity.LEGENDARY.value == "legendary"


def test_existing_items_default_to_common_rarity() -> None:
    # All four item kinds carry a `rarity` class-var defaulting to COMMON.
    assert Joker.rarity == Rarity.COMMON
    assert Planet.rarity == Rarity.COMMON
    assert Tarot.rarity == Rarity.COMMON
    assert Voucher.rarity == Rarity.COMMON
    # Joker also gets a `fusable` class-var (used by Phase 3 endless fusion).
    assert Joker.fusable is True


# ── New BelAtroRun fields ──────────────────────────────────────────────────


def test_belatro_run_has_phase1_fields_with_safe_defaults() -> None:
    run = BelAtroRun()
    assert run.tierce_charges == 0
    assert run.legendary_unlocked == set()
    assert run.endless is False
    assert run.endless_ante_offset == 0
    assert run.ante_theme is None
    assert run.capot_insurance is False
    assert run.partner_mood == "neutral"


# ── Event payload extensions ───────────────────────────────────────────────


def test_bid_made_event_carries_coinche_level() -> None:
    e = BidMadeEvent(
        seat=Seat.EAST,
        trump=Suit.HEARTS,
        contract="normal",
        coinche_level=2,
    )
    assert e.coinche_level == 2


def test_round_end_event_carries_contract_and_coinche_level() -> None:
    class _Stub:
        is_failed = False

    e = RoundEndEvent(
        breakdown=_Stub(),
        taker_seat=Seat.SOUTH,
        trump=Suit.TOUT_ATOUT,
        capot=False,
        contract="tout_atout",
        coinche_level=1,
    )
    assert e.contract == "tout_atout"
    assert e.coinche_level == 1
    assert e.trump == Suit.TOUT_ATOUT


# ── _SUIT_TO_CONTRACT mapping ──────────────────────────────────────────────


def test_suit_to_contract_includes_tout_atout() -> None:
    from belote.belatro.core.scoring import _SUIT_TO_CONTRACT

    assert _SUIT_TO_CONTRACT[Suit.TOUT_ATOUT] == "tout_atout"
