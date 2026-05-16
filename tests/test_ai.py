from __future__ import annotations

import unittest.mock

from belote.ai import AIPlayer, Difficulty
from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard


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


# ── C4: opp_trumps formula ───────────────────────────────────────────────────


def _capture_opp_trumps(player: AIPlayer, state: GameState) -> tuple[int, int]:
    """Run `_hard_play` and capture (my_trumps, opp_trumps) by patching
    `_score_card_play`. Returns the first call's args."""
    captured: dict[str, int] = {}

    def _capture(self, card, st, trump, trick, partner_winning, hsc, my_t, opp_t):  # type: ignore[no-untyped-def]
        captured.setdefault("my", my_t)
        captured.setdefault("opp", opp_t)
        return 0.0

    with unittest.mock.patch.object(AIPlayer, "_score_card_play", _capture):
        player._hard_play(state, state.hand_of(player.seat))
    return captured["my"], captured["opp"]


def test_opp_trumps_excludes_own_and_partner_hand() -> None:
    """C4 regression: pre-3.4.2, `opp_trumps = 8 - played_trumps` over-counted
    by treating South's own trumps and partner's visible trumps as still
    in opponents' hands. The fix subtracts both."""
    from belote.game import BossModifiers

    # South holds 1 trump (HEARTS), 1 non-trump (SPADES). North (partner)
    # is visible with 1 trump. 2 trumps already played. Lead Spades so the
    # leading-strategy branch is NOT triggered.
    south_hand = (
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.SPADES, Rank.SEVEN),
    )
    north_hand = (Card(Suit.HEARTS, Rank.SEVEN),)
    trick = (TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.KING)),)
    state = GameState(
        hands=(south_hand, (), north_hand, ()),
        current_trick=trick,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,
        boss_modifiers=BossModifiers(),
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # Plant 2 played trumps into memory.
    player.memory.played.add(Card(Suit.HEARTS, Rank.JACK))
    player.memory.played.add(Card(Suit.HEARTS, Rank.ACE))

    my, opp = _capture_opp_trumps(player, state)
    assert my == 1, f"expected my_trumps=1, got {my}"
    # 8 total - 1 mine - 2 played - 1 partner = 4 in opponents' hands.
    assert opp == 4, f"expected opp_trumps=4, got {opp}"


def test_opp_trumps_under_tout_atout_uses_32_total() -> None:
    """C4 regression: under Tout Atout every card is a trump, so the total
    is 32 not 8. Pre-3.4.2 the formula degraded to `8 - 0` always (because
    no card.suit equals `Suit.TOUT_ATOUT`)."""
    south_hand = (
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.EIGHT),
    )
    north_hand = (Card(Suit.DIAMONDS, Rank.NINE),)
    trick = (TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.KING)),)
    state = GameState(
        hands=(south_hand, (), north_hand, ()),
        current_trick=trick,
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=Suit.TOUT_ATOUT,
    )
    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player.update_memory(state)
    # 3 cards already played.
    player.memory.played.add(Card(Suit.HEARTS, Rank.ACE))
    player.memory.played.add(Card(Suit.DIAMONDS, Rank.TEN))
    player.memory.played.add(Card(Suit.SPADES, Rank.JACK))

    my, opp = _capture_opp_trumps(player, state)
    assert my == 2, f"expected my_trumps=2 (all hand cards under TA), got {my}"
    # 32 total - 2 mine - 4 played (1 from current_trick + 3 planted) - 1 partner = 25.
    assert opp == 25, f"expected opp_trumps=25, got {opp}"


# ── 3.9.3 R1: AI bid heuristics honor zero-rank boss flags ─────────────────


def _ta_jack_heavy_hand() -> tuple[Card, ...]:
    """8-card hand that's strong-for-TA: 3 Jacks across 3 suits + Aces.

    Under normal scoring this passes _hard_special's TA threshold (~50).
    Under `jacks_zero` (Le Sauvage) the Jacks score 0 and the hand should
    fall below threshold — the AI must NOT bid Tout Atout in that world.
    """
    return (
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.DIAMONDS, Rank.JACK),
        Card(Suit.CLUBS, Rank.NINE),
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.EIGHT),
    )


def test_hard_ai_bids_ta_on_jack_heavy_hand_under_normal_scoring() -> None:
    """Baseline: under normal scoring the heuristic picks Tout Atout."""
    hand = _ta_jack_heavy_hand()
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    state = GameState(
        hands=((), hand, (), ()),
        up_card=Card(Suit.CLUBS, Rank.SEVEN),
        bidding_round=2,
        bidder_index=2,
        dealer=Seat.SOUTH,
        boss_modifiers=BossModifiers(),
    )
    bid = player.decide_bid(state)
    assert bid == Suit.TOUT_ATOUT


def test_hard_ai_does_not_bid_ta_when_jacks_zero_suppresses_jacks() -> None:
    """3.9.3 R1 regression: under `jacks_zero` the Jacks score 0, so the
    Jack-heavy hand is no longer TA-worthy and the AI should pass on TA."""
    hand = _ta_jack_heavy_hand()
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    state = GameState(
        hands=((), hand, (), ()),
        up_card=Card(Suit.CLUBS, Rank.SEVEN),
        bidding_round=2,
        bidder_index=2,
        dealer=Seat.SOUTH,
        boss_modifiers=BossModifiers(jacks_zero=True),
    )
    bid = player.decide_bid(state)
    assert bid != Suit.TOUT_ATOUT, (
        "AI must not bid Tout Atout when jacks_zero suppresses the entire "
        "TA strength signal — pre-3.9.3 it ignored the boss flag and overbid."
    )


# ── 4.1.0: AI legal-cards safety net ───────────────────────────────────────


def test_hard_ai_avoids_clubs_bid_under_ban_clubs() -> None:
    """4.1.0 audit: under LesClubsBannis (BossModifiers.ban_clubs=True) all
    clubs score 0, so the AI's `_hard_bid` must NOT pick clubs even when the
    hand is club-heavy. The fix relies on `card_points_with_modifiers`
    returning 0 for any clubs card under the flag — the bid heuristic
    inherits the suppression automatically. This test pins that pipeline.
    """
    # Club-heavy hand that would normally score very well at Clubs trump:
    # Jack/Nine/Ace of Clubs (the three honors).
    hand = (
        Card(Suit.CLUBS, Rank.JACK),
        Card(Suit.CLUBS, Rank.NINE),
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.CLUBS, Rank.TEN),
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.EIGHT),
        Card(Suit.DIAMONDS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.SEVEN),
    )
    player = AIPlayer(Seat.EAST, Difficulty.HARD)
    state = GameState(
        hands=((), hand, (), ()),
        up_card=Card(Suit.SPADES, Rank.NINE),
        bidding_round=2,
        bidder_index=2,
        dealer=Seat.SOUTH,
        boss_modifiers=BossModifiers(ban_clubs=True),
    )
    bid = player.decide_bid(state)
    assert bid != Suit.CLUBS, (
        "AI must not bid Clubs under LesClubsBannis — `ban_clubs` zeros all "
        "club card points, so Clubs is the worst possible trump choice."
    )


def test_ai_legal_cards_empty_raises() -> None:
    """4.1.0 fix: when `legal_cards` returns an empty tuple mid-play (only
    possible if there's a dealing or legal-cards regression), the AI must
    raise rather than silently fall back to the full hand. Pre-4.1.0 the
    silent fallback let illegal-card bugs slip past the AI; the assertion
    surfaces them at decision time.

    We force the regression by monkey-patching `legal_cards` to return ().
    """
    import unittest.mock

    import pytest

    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    hand = (Card(Suit.HEARTS, Rank.SEVEN), Card(Suit.SPADES, Rank.ACE))
    state = GameState(
        hands=(hand, (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,
    )
    with (
        unittest.mock.patch("belote.ai.legal_cards", return_value=()),
        pytest.raises(AssertionError, match="legal_cards empty"),
    ):
        player.decide_card(state)


def test_ai_no_raw_card_points_import() -> None:
    """4.1.1 fix: `ai.py` must not import the raw `card_points` helper from
    `deck`. Every play-time card valuation routes through
    `card_points_with_modifiers` so zero-rank boss flags (kings_zero,
    aces_zero, jacks_zero, tens_zero, ban_clubs) propagate to discard /
    lead heuristics. Pre-4.1.1 the bid path migrated to the boss-aware
    helper but the play path still called raw `card_points_fn`.
    """
    import inspect

    import belote.ai as ai_mod

    src = inspect.getsource(ai_mod)
    assert "card_points as card_points_fn" not in src, (
        "ai.py must not re-import raw card_points — play heuristics must "
        "route through card_points_with_modifiers"
    )
    assert "card_points_fn(" not in src, (
        "ai.py contains a leftover card_points_fn(...) call — every play-"
        "time card valuation must use card_points_with_modifiers"
    )


def test_hard_ai_play_score_uses_jacks_zero() -> None:
    """4.1.1 fix: `_score_card_play` must read per-card value through
    `card_points_with_modifiers`, not raw `card_points`. The boss-modified
    points propagate into `_score_discarding_strategy` (`-points * 0.7`)
    and `_score_winning_strategy` (`-points * 0.4` or `-points * 0.9`),
    which are the branches that actually consult them.

    Under `jacks_zero` the Jack of trump is worth 0, not 20. In a partner-
    winning discard scenario the discarding-strategy penalty `-0.7 * pts`
    drops by 0.7 * 20 = 14.0 between the no-flag and jacks_zero states.
    """
    from belote.deck import Contract

    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player._se = False
    trump = Suit.HEARTS
    j_trump = Card(Suit.HEARTS, Rank.JACK)  # 20pts as trump

    # Partner (NORTH) leads SPADES.ACE (non-trump, partner is winning) →
    # `_score_card_play` routes to `_score_discarding_strategy` because
    # `partner_winning=True` and lead suit (SPADES) != trump (HEARTS).
    # The discarding penalty is `-points * 0.7`, so under jacks_zero the
    # score for J-trump must rise by 0.7 * 20 = 14.0.
    trick = (TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.ACE)),)

    state_no = GameState(
        hands=((j_trump,), (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract=Contract.NORMAL,
    )
    state_jz = GameState(
        hands=((j_trump,), (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract=Contract.NORMAL,
        boss_modifiers=BossModifiers(jacks_zero=True),
    )

    # (trick, partner_winning, hand_suit_counts, my_trumps, opp_trumps)
    args = (trick, True, {Suit.HEARTS: 1}, 1, 7)
    score_no = player._score_card_play(j_trump, state_no, trump, *args)
    score_jz = player._score_card_play(j_trump, state_jz, trump, *args)

    # discarding_strategy: -0.7 * pts. Under no flag pts=20 → -14;
    # under jacks_zero pts=0 → 0. score_jz - score_no = 14.0.
    delta = score_jz - score_no
    assert abs(delta - 14.0) < 1e-6, (
        f"Expected score delta = 14.0 (-0.7 * 20pts discard penalty wiped "
        f"under jacks_zero), got {delta}. If this fails, _score_card_play "
        f"is still computing `points` via raw card_points instead of "
        f"card_points_with_modifiers."
    )


def test_hard_ai_play_score_uses_ban_clubs() -> None:
    """4.1.1 fix: same wiring under `ban_clubs` — every clubs card scores 0,
    so the discarding-strategy penalty `-0.7 * pts` for A-clubs (11 raw)
    must drop to 0 under the flag. Delta = 0.7 * 11 = 7.7.
    """
    from belote.deck import Contract

    player = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    player._se = False
    trump = Suit.HEARTS
    a_clubs = Card(Suit.CLUBS, Rank.ACE)  # 11pts non-trump

    trick = (TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.KING)),)

    state_no = GameState(
        hands=((a_clubs,), (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract=Contract.NORMAL,
    )
    state_ban = GameState(
        hands=((a_clubs,), (), (), ()),
        turn=Seat.SOUTH,
        phase=Phase.PLAYING,
        trump=trump,
        contract=Contract.NORMAL,
        boss_modifiers=BossModifiers(ban_clubs=True),
    )

    args = (trick, True, {Suit.CLUBS: 1}, 0, 8)
    score_no = player._score_card_play(a_clubs, state_no, trump, *args)
    score_ban = player._score_card_play(a_clubs, state_ban, trump, *args)

    delta = score_ban - score_no
    assert abs(delta - 7.7) < 1e-6, (
        f"Expected score delta = 7.7 (-0.7 * 11pts discard penalty wiped "
        f"under ban_clubs), got {delta}. _score_card_play must thread "
        f"card_points_with_modifiers into the discarding-strategy `points` "
        f"parameter."
    )


def test_medium_ai_discard_consults_boss_modifier_helper() -> None:
    """4.1.1 fix: `_medium_play`'s discard `min()` at the two no-trump-led
    void-in-trump branches must route through `card_points_with_modifiers`.
    Pre-4.1.1 the lambda called raw `card_points_fn`, so under kings_zero
    the AI preserved a K (raw 4-pt off-suit value) instead of treating it
    as a 0-pt discard candidate.

    We pin the wiring by stubbing `belote.ai.card_points_with_modifiers`
    and asserting `_medium_play` calls it at least once for the discard
    decision. The earlier import-line test pins that raw `card_points_fn`
    is gone; this one pins the replacement is wired correctly.
    """
    from belote.deck import Contract

    # Hand: K-clubs + 7-clubs. Lead is trump (Hearts ACE) so the AI is
    # void in trump → falls through to the line-418 discard branch
    # (`No trumps, discard low non-trump`).
    hand = (Card(Suit.CLUBS, Rank.KING), Card(Suit.CLUBS, Rank.SEVEN))
    state = GameState(
        hands=((), (), (), hand),  # WEST holds the hand
        turn=Seat.WEST,
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,
        contract=Contract.NORMAL,
        current_trick=(TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),),
        boss_modifiers=BossModifiers(kings_zero=True),
    )
    player = AIPlayer(Seat.WEST, Difficulty.MEDIUM)

    import belote.ai as ai_mod

    real_helper = ai_mod.card_points_with_modifiers
    calls: list[tuple] = []

    def wrapper(card, trump, bm):  # type: ignore[no-untyped-def]
        calls.append((card, trump, bm))
        return real_helper(card, trump, bm)

    with unittest.mock.patch.object(ai_mod, "card_points_with_modifiers", wrapper):
        player.decide_card(state)

    assert calls, (
        "Medium AI's discard heuristic must consult "
        "card_points_with_modifiers (4.1.1) — pre-fix it called raw "
        "card_points_fn and so was blind to zero-rank boss flags."
    )
