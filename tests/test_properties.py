from __future__ import annotations

import random

from belote.deck import Suit, card_points, deal, make_deck, shuffle
from belote.game import (
    Phase,
    legal_cards,
    new_game,
    place_bid,
    play_card,
    start_round,
)
from belote.scoring import score_round


def test_point_conservation_property() -> None:
    """Total card points must always be 152 for any deal."""
    deck = make_deck()
    for _ in range(20):  # 20 random deals
        rng = random.Random()
        shuffled = shuffle(deck, rng)
        hands, up_card, remaining = deal(shuffled)

        # Iterate over standard card-suit trumps only; TOUT_ATOUT scores every
        # card as trump and intentionally breaks the 152 invariant.
        for trump in up_card.suit.__class__:
            if not trump.is_card_suit:
                continue
            total = card_points(up_card, trump)
            for hand in hands:
                total += sum(card_points(c, trump) for c in hand)
            total += sum(card_points(c, trump) for c in remaining)
            assert total == 152


def test_legal_moves_never_empty() -> None:
    """In PLAYING phase, legal_cards() should never return an empty tuple if hand is not empty."""
    for _ in range(5):  # 5 full game simulations
        rng = random.Random()
        state = start_round(new_game(), rng)

        # Mock taking the first suit to enter PLAYING phase
        from belote.game import place_bid

        state = place_bid(state, state.up_card.suit)

        while state.phase == Phase.PLAYING:
            seat = state.turn
            hand = state.hand_of(seat)
            # An empty hand mid-PLAYING is a deal/play bug; surface it loudly
            # rather than silently bailing.
            assert hand, (
                f"Empty hand for {seat} mid-PLAYING at trick "
                f"{len(state.completed_tricks)} — invariant violation"
            )

            legal = legal_cards(state, seat)
            assert len(legal) > 0, (
                f"No legal moves for {seat} with hand {hand} at trick {len(state.completed_tricks)}"
            )

            # Play a random legal card (use the seeded rng for determinism).
            card = rng.choice(legal)
            state = play_card(state, card)


# ---------------------------------------------------------------------------
# 3.3.3 T1 — Post-round scoring invariants
#
# Drive seeded rounds to completion via the same legal_cards + play_card loop
# as test_legal_moves_never_empty, then assert post-round invariants. These
# are the kind of property tests that would have caught the L'Anarchie belote
# zero (3.3.1) and the La Rupture HUD divergence (3.3.1/3.3.2) years earlier
# had they existed at the time.
# ---------------------------------------------------------------------------


def _drive_full_round(rng: random.Random, contract_bid: object) -> object:
    """Play a complete round to terminal phase under the given first-bid.

    `contract_bid` is whatever `place_bid` accepts: a card Suit (normal),
    `Suit.TOUT_ATOUT`, or `"sans_atout"`. TA/SA are only legal in round 2,
    so for those we pass 4× to step into round 2 first.
    """
    state = start_round(new_game(), rng)
    is_round_2_only = contract_bid == Suit.TOUT_ATOUT or contract_bid == "sans_atout"
    if is_round_2_only:
        for _ in range(4):
            state = place_bid(state, None)
    state = place_bid(state, contract_bid)
    while state.phase == Phase.PLAYING:
        seat = state.turn
        legal = legal_cards(state, seat)
        assert legal, f"No legal moves for {seat} — deal/play bug"
        card = rng.choice(legal)
        state = play_card(state, card)
    return state


def test_full_round_consumes_every_card_normal_contract() -> None:
    """Invariant: after a full round under a normal contract, every hand is
    empty and exactly 8 completed tricks are recorded. Trip-wire for any
    bug that leaks a card or short-circuits a trick.
    """
    for seed in range(15):
        rng = random.Random(seed)
        state = _drive_full_round(rng, Suit.SPADES)
        # Every hand should be drained.
        for seat_idx, hand in enumerate(state.hands):
            assert hand == (), f"seed={seed}: seat {seat_idx} still holds {hand}"
        # 8 tricks complete.
        assert len(state.completed_tricks) == 8, (
            f"seed={seed}: expected 8 tricks, got {len(state.completed_tricks)}"
        )


def test_score_round_sums_to_card_total_normal_contract() -> None:
    """Invariant: for a successful (non-litige, non-zero-table) normal-suit
    contract, table_taker_pts + table_defender_pts = 162 (152 card pts +
    10 dix de der). Boss zero-rank flags would lower this; with no boss
    active and a normal contract, the sum is exact.
    """
    for seed in range(15):
        rng = random.Random(seed)
        state = _drive_full_round(rng, Suit.SPADES)
        bd = score_round(state)
        table_total = bd.table_taker_pts + bd.table_defender_pts
        # 152 card pts + 10 dix de der = 162. The card-point conservation
        # property (152) is already pinned by test_point_conservation_property;
        # this extends it through scoring to include the last-trick bonus.
        assert table_total == 162, (
            f"seed={seed}: table_taker+defender = {table_total}, expected 162"
        )


def test_score_round_sums_to_card_total_tout_atout() -> None:
    """Invariant: Tout Atout deck = 248 card pts (every card on trump scale)
    + 10 dix de der = 258. The 3.3.3 sort_hand TA fix (F1) is upstream of
    this — it doesn't change scoring, but if the TA branch ever bled into
    card_points the invariant would break and surface here.
    """
    for seed in range(15):
        rng = random.Random(seed)
        state = _drive_full_round(rng, Suit.TOUT_ATOUT)
        bd = score_round(state)
        table_total = bd.table_taker_pts + bd.table_defender_pts
        assert table_total == 258, (
            f"seed={seed}: TA table_taker+defender = {table_total}, expected 258"
        )


def test_score_round_sums_to_card_total_sans_atout() -> None:
    """Invariant: Sans Atout deck = 120 card pts (every card on non-trump
    scale, 30 per suit × 4) + 10 dix de der = 130. Pin against the
    L'Anarchie-style "scoring keys on rotated trump" class of bug.
    (`config.TOTAL_POINTS_SANS_ATOUT` is the authoritative constant.)
    """
    for seed in range(15):
        rng = random.Random(seed)
        state = _drive_full_round(rng, "sans_atout")
        bd = score_round(state)
        table_total = bd.table_taker_pts + bd.table_defender_pts
        assert table_total == 130, (
            f"seed={seed}: SA table_taker+defender = {table_total}, expected 130"
        )
