"""Property tests for the few coverage gaps the 3.9.5 audit identified.

`test_properties.py` already covers point conservation across contracts, the
La Rupture HUD/scoring consistency, and the L'Anarchie SA invariant. The tests
here add:

* Combined boss-modifier robustness — drive a full round under random pairs
  of boss flags and assert no crash + state coherence.
* La Rupture vs. capot impossibility — under `no_consecutive_team_wins` the
  same team cannot win two consecutive tricks, so capot is unreachable.
* L'Anarchie + no_belote — when both flags are active, belote/rebelote must
  remain fully suppressed regardless of trump rotation.
"""

from __future__ import annotations

import itertools
import random

from belote.deck import Suit
from belote.game import (
    BossModifiers,
    Phase,
    legal_cards,
    new_game,
    place_bid,
    play_card,
    replace,
    start_round,
)
from belote.scoring import score_round


def _drive(rng: random.Random, bm: BossModifiers, contract_bid: object = Suit.SPADES) -> object:
    """Run a full round under the given boss modifiers."""
    state = start_round(new_game(), rng)
    state = replace(state, boss_modifiers=bm)
    is_round_2_only = contract_bid == Suit.TOUT_ATOUT or contract_bid == "sans_atout"
    if is_round_2_only:
        for _ in range(4):
            state = place_bid(state, None)
    state = place_bid(state, contract_bid)
    state = replace(state, boss_modifiers=bm)  # bid preserves modifiers, but pin again to be safe
    while state.phase == Phase.PLAYING:
        seat = state.turn
        legal = legal_cards(state, seat)
        assert legal, f"No legal moves for {seat} under {bm}"
        state = play_card(state, rng.choice(legal))
    return state


# ---------------------------------------------------------------------------
# Boss-modifier pair robustness
# ---------------------------------------------------------------------------

_SAFE_FLAGS = (
    "no_belote",
    "no_consecutive_team_wins",
    "kings_zero",
    "aces_zero",
    "jacks_zero",
    "tens_zero",
    "ban_clubs",
    "no_dix_de_der",
    "declarations_zero",
)


def test_boss_modifier_pairs_complete_round() -> None:
    """Driving a full round under any pair of zero-or-suppression flags must
    not crash, must drain all hands, and must yield a scoreable state.
    """
    for flag_a, flag_b in itertools.combinations(_SAFE_FLAGS, 2):
        bm = BossModifiers(**{flag_a: True, flag_b: True})
        rng = random.Random(hash((flag_a, flag_b)) & 0xFFFF)
        state = _drive(rng, bm, Suit.SPADES)
        assert len(state.completed_tricks) == 8, (
            f"{flag_a}+{flag_b}: tricks={len(state.completed_tricks)}"
        )
        for hand in state.hands:
            assert hand == (), f"{flag_a}+{flag_b}: hand not drained: {hand}"
        bd = score_round(state)
        assert bd is not None, f"{flag_a}+{flag_b}: scoring returned None"


# ---------------------------------------------------------------------------
# La Rupture excludes capot
# ---------------------------------------------------------------------------


def test_la_rupture_makes_capot_unreachable() -> None:
    """Under `no_consecutive_team_wins`, the same team cannot win two
    consecutive tricks. With 8 tricks the longest run for one team is
    therefore 4 (every other trick) — capot (all 8) is impossible.
    """
    for seed in range(25):
        rng = random.Random(seed)
        bm = BossModifiers(no_consecutive_team_wins=True)
        state = _drive(rng, bm, Suit.SPADES)
        bd = score_round(state)
        assert not bd.is_capot, (
            f"seed={seed}: capot fired under La Rupture (impossible by rule)"
        )


# ---------------------------------------------------------------------------
# L'Anarchie + no_belote: rotation never resurrects belote
# ---------------------------------------------------------------------------


def test_anarchie_plus_no_belote_suppresses_belote_across_rotations() -> None:
    """Even with trump rotating every 2 tricks under L'Anarchie, `no_belote`
    must keep belote_tracker fully false through the entire round.
    """
    for seed in range(15):
        rng = random.Random(seed)
        bm = BossModifiers(dynamic_trump=True, no_belote=True)
        state = _drive(rng, bm, Suit.SPADES)
        assert state.belote_tracker == (False, False), (
            f"seed={seed}: belote fired despite no_belote under L'Anarchie: "
            f"tracker={state.belote_tracker}"
        )


# ---------------------------------------------------------------------------
# Zero-rank invariants: total points decrease, never increase
# ---------------------------------------------------------------------------


def test_zero_rank_flags_never_increase_table_total() -> None:
    """A zero-rank flag (kings_zero, aces_zero, jacks_zero, tens_zero) can
    only remove points from the table sum — it must never push the total
    above the no-flag baseline of 162 (normal contract, 152 + dix de der).
    """
    for flag in ("kings_zero", "aces_zero", "jacks_zero", "tens_zero"):
        for seed in range(8):
            rng = random.Random(seed * 7 + hash(flag) & 0xFF)
            bm = BossModifiers(**{flag: True})
            state = _drive(rng, bm, Suit.SPADES)
            bd = score_round(state)
            total = bd.table_taker_pts + bd.table_defender_pts
            assert total <= 162, (
                f"{flag} seed={seed}: table total {total} exceeded 162 baseline"
            )
