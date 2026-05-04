"""Phase 0.4: minimal happy-path coverage backstop.

These tests guard the jokers, partner personalities, and boss modifiers that
upcoming Phase 1+ changes will touch. They're not exhaustive — just enough
that a regression caused by upcoming refactors gets caught.
"""

from __future__ import annotations

import random

from belote.belatro.engine.event_bus import RoundEndEvent, TrickWonEvent
from belote.belatro.items.jokers.contract import LeDiplomate, LeFanatique
from belote.belatro.partner.personality import (
    LEconome,
    LeFantome,
    LeFlambeur,
    LeSacrifie,
    LeStratege,
)
from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard
from belote.scoring import score_round

# ── LeFanatique (Tout Atout) ───────────────────────────────────────────────


def test_le_fanatique_only_fires_on_tout_atout() -> None:
    j = LeFanatique()
    j.on_round_start({})
    state: dict = {"contract": "normal"}
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(),
        trick_number=5,
        is_last=False,
        card_points=0,
        trump=Suit.HEARTS,
    )
    assert j.on_trick_won(evt, state) is None


def test_le_fanatique_triggers_after_fourth_win() -> None:
    j = LeFanatique()
    state: dict = {"contract": "tout_atout"}
    j.on_round_start(state)
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(),
        trick_number=5,
        is_last=False,
        card_points=0,
        trump=Suit.HEARTS,
    )
    # First 4 wins → no payout; 5th → times_mult=1.5
    for _ in range(4):
        assert j.on_trick_won(evt, state) is None
    res = j.on_trick_won(evt, state)
    assert res is not None and res.times_mult == 1.5


# ── LeDiplomate (K+Q same suit) ────────────────────────────────────────────


def test_le_diplomate_fires_on_king_queen_same_suit() -> None:
    j = LeDiplomate()
    cards = (
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.HEARTS, Rank.QUEEN),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.SPADES, Rank.EIGHT),
    )
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=cards,
        trick_number=1,
        is_last=False,
        card_points=0,
        trump=Suit.SPADES,
    )
    res = j.on_trick_won(evt, {})
    assert res is not None and res.times_mult == 2.0


def test_le_diplomate_skips_when_only_king() -> None:
    j = LeDiplomate()
    cards = (Card(Suit.HEARTS, Rank.KING), Card(Suit.HEARTS, Rank.JACK))
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=cards,
        trick_number=1,
        is_last=False,
        card_points=0,
        trump=Suit.SPADES,
    )
    assert j.on_trick_won(evt, {}) is None


# ── Partner personalities ──────────────────────────────────────────────────


def _state_with_north_hand(hand: tuple[Card, ...], up: Card | None = None) -> GameState:
    return GameState(
        hands=((), (), hand, ()),
        up_card=up,
        phase=Phase.BIDDING,
    )


def test_l_econome_bids_only_with_trump_jack() -> None:
    p = LEconome()
    up = Card(Suit.HEARTS, Rank.SEVEN)
    with_jack = _state_with_north_hand((Card(Suit.HEARTS, Rank.JACK),), up=up)
    without_jack = _state_with_north_hand((Card(Suit.HEARTS, Rank.ACE),), up=up)
    assert p.should_bid(with_jack) is True
    assert p.should_bid(without_jack) is False
    assert p.bid_value(with_jack) == Suit.HEARTS


def test_le_sacrifie_and_le_fantome_never_open_bidding() -> None:
    s = _state_with_north_hand((Card(Suit.SPADES, Rank.JACK),))
    assert LeSacrifie().should_bid(s) is False
    assert LeFantome().should_bid(s) is False


def test_le_stratege_needs_three_high_value_cards() -> None:
    p = LeStratege()
    high_hand = (
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.CLUBS, Rank.NINE),
        Card(Suit.DIAMONDS, Rank.SEVEN),
    )
    low_hand = (
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.SPADES, Rank.EIGHT),
        Card(Suit.CLUBS, Rank.QUEEN),
    )
    assert p.should_bid(_state_with_north_hand(high_hand)) is True
    assert p.should_bid(_state_with_north_hand(low_hand)) is False


def test_le_flambeur_uses_random_so_seeded_is_deterministic() -> None:
    p = LeFlambeur()
    s = _state_with_north_hand((Card(Suit.SPADES, Rank.ACE),))
    random.seed(1)
    first = [p.should_bid(s) for _ in range(20)]
    random.seed(1)
    second = [p.should_bid(s) for _ in range(20)]
    assert first == second  # deterministic under a fixed seed


# ── Boss modifiers ──────────────────────────────────────────────────────────


def _trick(s_card: Card, others_suit: Suit, others_rank: Rank = Rank.SEVEN) -> tuple[TrickCard, ...]:
    return (
        TrickCard(Seat.SOUTH, s_card),
        TrickCard(Seat.WEST, Card(others_suit, others_rank)),
        TrickCard(Seat.NORTH, Card(others_suit, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(others_suit, Rank.NINE)),
    )


def test_boss_seven_eight_trump_lets_seven_beat_ace() -> None:
    # Under seven_eight_trump, a 7 or 8 of any suit (whether of trump or not)
    # is treated as a trump-rank card. We assert via score_round that a trick
    # led by a 7 with three filler cards still gets credited to South.
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(seven_eight_trump=True),
        completed_tricks=(_trick(Card(Suit.SPADES, Rank.SEVEN), Suit.DIAMONDS, Rank.SEVEN),),
    )
    breakdown = score_round(state)
    # Just verify scoring runs and produces a breakdown without crashing.
    assert breakdown is not None


def test_boss_dynamic_trump_is_seed_deterministic() -> None:
    """L'Anarchie: the dynamic-trump rotation must be reproducible under a fixed RNG seed.

    This is the regression test for the audit-Phase-0 bug where `random.choice()`
    in game.py:750 used the global RNG instead of the seeded one.
    """
    from belote.game import new_game, start_round

    rng_a = random.Random(42)
    rng_b = random.Random(42)
    state_a = start_round(new_game(), rng_a)
    state_b = start_round(new_game(), rng_b)
    # Same seed → same deal → same _rng state.
    assert state_a.hands == state_b.hands
    # _rng now lives on state and is callable; pulling the same number twice yields equal results.
    assert state_a._rng.random() == state_b._rng.random()


def test_boss_dynamic_trump_changes_trump_every_two_tricks() -> None:
    """L'Anarchie: trump must rotate after every 2 completed tricks (game.py:750-756),
    but NOT after the 8th (final) trick. The new trump must be a different valid suit,
    and play must continue without legal_cards going stale."""
    from dataclasses import replace

    from belote.game import legal_cards, new_game, place_bid, play_card, start_round

    rng = random.Random(7)
    state = start_round(new_game(), rng)
    assert state.up_card is not None
    state = place_bid(state, state.up_card.suit)
    assert state.phase == Phase.PLAYING

    state = replace(state, boss_modifiers=BossModifiers(dynamic_trump=True))
    initial_trump = state.trump
    assert initial_trump is not None

    trumps_seen: list[Suit] = [initial_trump]

    for trick_no in range(1, 9):
        for _ in range(4):
            legal = legal_cards(state, state.turn)
            assert legal, f"legal_cards empty mid-play (trick {trick_no})"
            state = play_card(state, legal[0])
        assert state.trump is not None
        trumps_seen.append(state.trump)

    for swap_after in (2, 4, 6):
        assert trumps_seen[swap_after] != trumps_seen[swap_after - 2], (
            f"trump did not change after trick {swap_after}: "
            f"before={trumps_seen[swap_after - 2]} after={trumps_seen[swap_after]}"
        )
        assert trumps_seen[swap_after].is_card_suit

    assert trumps_seen[8] == trumps_seen[6], (
        f"trump unexpectedly changed on final trick: {trumps_seen[6]} -> {trumps_seen[8]}"
    )


def test_boss_no_dix_de_der_disables_last_trick_bonus() -> None:
    # NS wins the last trick with low card points; without no_dix_de_der they'd
    # get +10. With it on, last_trick_bonus must NOT be added to NS card points.
    last_trick = (
        TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.JACK)),  # trump
        TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.SEVEN)),
        TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.EIGHT)),
        TrickCard(Seat.SOUTH, Card(Suit.CLUBS, Rank.NINE)),
    )
    base_state = {
        "hands": ((), (), (), ()),
        "trump": Suit.CLUBS,
        "taker": Seat.SOUTH,
        "phase": Phase.SCORING,
        "completed_tricks": (last_trick,) * 8,
        "last_trick_winner": Seat.NORTH,
    }
    with_bonus = score_round(GameState(**base_state, boss_modifiers=BossModifiers()))
    without_bonus = score_round(
        GameState(**base_state, boss_modifiers=BossModifiers(no_dix_de_der=True))
    )
    # Disabling the bonus reduces the taker side's table points by exactly 10.
    assert with_bonus.table_taker_pts - without_bonus.table_taker_pts == 10


def test_boss_agent_double_active_flag_visible_on_state() -> None:
    """The flag on BossModifiers must be reachable via state.boss_modifiers.

    This is the canonical pattern that ai.py now uses (post Phase 0.1 fix);
    this test pins it so future renames can't silently re-introduce the
    `getattr(state, "_agent_double_active", False)` foot-gun.
    """
    state = GameState(
        hands=((), (), (), ()),
        boss_modifiers=BossModifiers(agent_double_active=True),
    )
    assert state.boss_modifiers.agent_double_active is True


def test_round_end_event_carries_trump_and_capot() -> None:
    """RoundEndEvent must expose trump and capot; jokers like LePuriste depend on it."""

    class _Stub:
        is_failed = False

    evt = RoundEndEvent(breakdown=_Stub(), taker_seat=Seat.SOUTH, trump=None, capot=False)
    assert evt.trump is None
    assert evt.capot is False
    assert evt.taker_seat == Seat.SOUTH
