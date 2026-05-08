from __future__ import annotations

import unittest.mock

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, Suit
from belote.game import GameState, Phase, Seat, TrickCard


def test_ai_easy_play() -> None:
    player = AIPlayer(Seat.EAST, Difficulty.EASY)
    hand = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.ACE))
    state = GameState(
        hands=((), hand, (), ()), turn=Seat.EAST, phase=Phase.PLAYING, trump=Suit.HEARTS
    )
    # Easy AI should pick a random legal card
    # We mock rng to ensure it picks the first one
    with unittest.mock.patch.object(player._rng, "choice", side_effect=lambda x: x[0]):
        card = player.decide_card(state)
        assert card == Card(Suit.HEARTS, Rank.SEVEN)


def test_ai_medium_bid() -> None:
    player = AIPlayer(Seat.EAST, Difficulty.MEDIUM)
    # Give it a strong hearts hand
    hand = (
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.DIAMONDS, Rank.SEVEN),
    )
    up_card = Card(Suit.HEARTS, Rank.TEN)
    state = GameState(
        hands=((), hand, (), ()),
        up_card=up_card,
        bidding_round=1,
        bidder_index=1,
        dealer=Seat.SOUTH,
    )
    bid = player.decide_bid(state)
    assert bid == Suit.HEARTS


def test_ai_medium_play_follows_suit() -> None:
    player = AIPlayer(Seat.EAST, Difficulty.MEDIUM)
    hand = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.ACE))
    state = GameState(
        hands=((), hand, (), ()),
        turn=Seat.EAST,
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS,
        current_trick=(TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),),
    )
    # Must follow hearts
    card = player.decide_card(state)
    assert card == Card(Suit.HEARTS, Rank.SEVEN)


def test_ai_hard_void_inference() -> None:
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    # South leads Spades, West (partner of East) doesn't follow
    trick1 = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.TEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),  # West void in Spades
    )
    state = GameState(
        hands=[(), (), (), ()], completed_tricks=(trick1,), phase=Phase.PLAYING, trump=Suit.DIAMONDS
    )
    player._update_voids(state)
    assert Suit.SPADES in player.memory.known_voids[Seat.WEST]


def test_ai_void_inference_skips_wild_seven_under_republicain() -> None:
    """Republicain wild: a 7 played off-suit doesn't prove void in lead suit."""
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    trick1 = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        # West plays a 7 of hearts off-suit. Under republicain_wild this is a
        # legal "wild" — does NOT imply West is void in spades.
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
    )
    state = GameState(
        hands=[(), (), (), ()],
        completed_tricks=(trick1,),
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS,
        _joker_state={"republicain_wild": True},
    )
    player._update_voids(state)
    # No void should be inferred for West.
    assert Suit.SPADES not in player.memory.known_voids[Seat.WEST]


def test_void_cache_invalidates_across_rounds() -> None:
    """A new round must NOT inherit the previous round's last_voids_key —
    otherwise _update_voids may skip processing on a coincidental match."""
    player = AIPlayer(Seat.EAST, Difficulty.HARD)

    # Simulate a completed round 1 leaving a stale key.
    player.memory.last_voids_key = (0, 1)
    player.memory.processed_tricks_count = 8
    # Plant a stale void (West "void" in spades from the prior round).
    player.memory.known_voids[Seat.WEST].add(Suit.SPADES)

    # Round 2 begins — empty completed/current.
    fresh = GameState(
        hands=[(), (), (), ()],
        completed_tricks=(),
        current_trick=(),
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS,
    )
    player.update_memory(fresh)

    # The stale void must have been cleared by the new-round reset.
    assert Suit.SPADES not in player.memory.known_voids[Seat.WEST]
    # The cache key must have been invalidated so _update_voids() will run.
    assert player.memory.last_voids_key is None


def test_ai_void_inference_still_flags_non_wild_offsuit_under_republicain() -> None:
    """Under republicain_wild, off-suit non-7/8 cards still prove void."""
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    trick1 = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.JACK)),  # Jack — not wild
    )
    state = GameState(
        hands=[(), (), (), ()],
        completed_tricks=(trick1,),
        phase=Phase.PLAYING,
        trump=Suit.DIAMONDS,
        _joker_state={"republicain_wild": True},
    )
    player._update_voids(state)
    assert Suit.SPADES in player.memory.known_voids[Seat.WEST]


# ── F5: AI bidding for Tout Atout / Sans Atout ─────────────────────────────


def _bid_state(hand, bidder_index=0, up_card=None, bidding_round=2):
    hands = [(), (), (), ()]
    hands[Seat.EAST.value] = hand
    return GameState(
        hands=tuple(hands),
        up_card=up_card,
        bidding_round=bidding_round,
        bidder_index=bidder_index,
        dealer=Seat.SOUTH,
    )


def test_ai_round1_never_bids_tout_atout() -> None:
    """Round 1 must reject TA/SA — they're round-2-only contracts."""
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    # Strong TA-shaped hand: lots of Jacks
    hand = (
        Card(Suit.HEARTS, Rank.JACK), Card(Suit.SPADES, Rank.JACK),
        Card(Suit.DIAMONDS, Rank.JACK), Card(Suit.CLUBS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE), Card(Suit.SPADES, Rank.NINE),
        Card(Suit.DIAMONDS, Rank.ACE), Card(Suit.CLUBS, Rank.ACE),
    )
    state = _bid_state(hand, up_card=Card(Suit.HEARTS, Rank.TEN), bidding_round=1)
    # Round 1: even if AI loves TA, the up-card is HEARTS, so it can only take HEARTS.
    bid = player.decide_bid(state)
    assert bid in (Suit.HEARTS, None), f"unexpected round-1 bid: {bid}"


def test_ai_hard_bids_tout_atout_on_jack_heavy_hand() -> None:
    """All four Jacks plus Aces should trigger Tout Atout in round 2."""
    from belote.game import SANS_ATOUT_BID  # noqa: F401 (used elsewhere)
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    hand = (
        Card(Suit.HEARTS, Rank.JACK), Card(Suit.SPADES, Rank.JACK),
        Card(Suit.DIAMONDS, Rank.JACK), Card(Suit.CLUBS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE), Card(Suit.SPADES, Rank.NINE),
        Card(Suit.DIAMONDS, Rank.ACE), Card(Suit.CLUBS, Rank.ACE),
    )
    state = _bid_state(hand, bidder_index=3)  # last to bid → aggression bonus
    bid = player.decide_bid(state)
    assert bid == Suit.TOUT_ATOUT


def test_ai_easy_bids_sans_atout_on_flat_ace_hand() -> None:
    """Three Aces across three suits with no long suit → Sans Atout."""
    from belote.game import SANS_ATOUT_BID
    player = AIPlayer(Seat.EAST, Difficulty.EASY)
    hand = (
        Card(Suit.HEARTS, Rank.ACE), Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.ACE), Card(Suit.SPADES, Rank.EIGHT),
        Card(Suit.DIAMONDS, Rank.ACE), Card(Suit.DIAMONDS, Rank.NINE),
        Card(Suit.CLUBS, Rank.SEVEN), Card(Suit.CLUBS, Rank.EIGHT),
    )
    state = _bid_state(hand)
    bid = player.decide_bid(state)
    assert bid == SANS_ATOUT_BID


def test_ai_pass_on_weak_hand() -> None:
    """A weak hand should not bid TA, SA, or any suit."""
    player = AIPlayer(Seat.EAST, Difficulty.MEDIUM)
    hand = (
        Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.HEARTS, Rank.EIGHT),
        Card(Suit.SPADES, Rank.SEVEN), Card(Suit.SPADES, Rank.EIGHT),
        Card(Suit.DIAMONDS, Rank.SEVEN), Card(Suit.DIAMONDS, Rank.EIGHT),
        Card(Suit.CLUBS, Rank.SEVEN), Card(Suit.CLUBS, Rank.EIGHT),
    )
    state = _bid_state(hand)
    # Force personality jitter to its extreme negative so the test isn't flaky.
    with unittest.mock.patch.object(player._rng, "uniform", return_value=-0.5):
        bid = player.decide_bid(state)
    assert bid is None
