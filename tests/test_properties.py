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


# ---------------------------------------------------------------------------
# 3.6.0 audit T1 — additional invariants
# ---------------------------------------------------------------------------


def test_chute_and_capot_are_mutually_exclusive() -> None:
    """Invariant: a single round outcome cannot be both `is_capot` AND
    `is_failed`-as-defender-capot AND credit the taker. Specifically,
    `is_capot=True AND is_failed=True` means the defenders capot'd the
    taker — a valid combination — but credit_taker_pts must then be 0.
    """
    for seed in range(30):
        rng = random.Random(seed)
        state = _drive_full_round(rng, Suit.SPADES)
        bd = score_round(state)
        if bd.is_capot and bd.is_failed:
            # Defender capot. Taker earns 0 card-pts credit.
            assert bd.credit_taker_pts == 0, (
                f"seed={seed}: defender capot but credit_taker_pts={bd.credit_taker_pts}"
            )
        if bd.is_capot and not bd.is_failed:
            # Taker capot. Defenders earn 0 card-pts credit.
            assert bd.credit_defender_pts == 0, (
                f"seed={seed}: taker capot but credit_defender_pts={bd.credit_defender_pts}"
            )


def test_dynamic_trump_never_overrides_sans_atout() -> None:
    """The `dynamic_trump` boss (L'Anarchie) rotates trump every 2 tricks,
    but Sans Atout intentionally has `trump=None`. Silently flipping
    trump to a real suit mid-round would break the SA contract. This
    test exercises a full SA round under `dynamic_trump` and asserts
    `state.trump is None` at every step.
    """
    from belote.game import BossModifiers, new_game, start_round

    rng = random.Random(11)
    state = start_round(new_game(), rng)
    # Step to round 2 (SA legal there only) then bid SA.
    for _ in range(4):
        state = place_bid(state, None)
    state = place_bid(state, "sans_atout")
    # Inject dynamic_trump after bid (would normally be set by boss apply).
    from dataclasses import replace as dc_replace
    state = dc_replace(
        state, boss_modifiers=BossModifiers(dynamic_trump=True)
    )

    while state.phase == Phase.PLAYING:
        assert state.trump is None, (
            "Sans Atout invariant: state.trump must remain None even under "
            f"dynamic_trump (current trump={state.trump})"
        )
        legal = legal_cards(state, state.turn)
        assert legal
        state = play_card(state, rng.choice(legal))


def test_no_consecutive_team_wins_invariant_when_rupture_active() -> None:
    """When the `no_consecutive_team_wins` (La Rupture) boss flag is on,
    the 8th-trick winner must flip teams if the first 7 tricks all went
    to one side. We don't simulate the full path-dependent rupture
    behaviour here — that's covered by the boss integration tests; the
    invariant we lock is: under Rupture, no team can sweep all 8 tricks.
    """
    from belote.game import BossModifiers, new_game, start_round, team_of

    sweeps = 0
    for seed in range(30):
        rng = random.Random(seed)
        state = start_round(new_game(), rng)
        from dataclasses import replace as dc_replace
        state = dc_replace(
            state, boss_modifiers=BossModifiers(no_consecutive_team_wins=True)
        )
        state = place_bid(state, state.up_card.suit)
        while state.phase == Phase.PLAYING:
            legal = legal_cards(state, state.turn)
            state = play_card(state, rng.choice(legal))
        # Compute trick winners ourselves so we don't rely on score internals.
        from belote.game import compute_trick_winners

        winners = compute_trick_winners(state, state.trump, False)
        ns = sum(1 for w in winners if w is not None and team_of(w) == 0)
        ew = sum(1 for w in winners if w is not None and team_of(w) == 1)
        assert ns < 8 and ew < 8, (
            f"seed={seed}: Rupture invariant violated — one team swept all 8 "
            f"tricks (NS={ns}, EW={ew})"
        )
        if ns == 8 or ew == 8:
            sweeps += 1
    assert sweeps == 0
