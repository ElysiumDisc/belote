"""Boss modifier integration tests."""

from __future__ import annotations

from dataclasses import replace

from belote.deck import Card, Rank, Suit
from belote.game import BossModifiers, GameState, Phase, Seat, TrickCard
from belote.scoring import is_capot, score_round


def test_boss_no_belote():
    """1. Boss: No Belote - Verify belote points are suppressed."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(no_belote=True),
        belote_holders={Suit.HEARTS: Seat.SOUTH},
        belote_tracker=(True, True)
    )
    breakdown = score_round(state)
    assert not any("Belote" in m for m in breakdown.messages)
    assert breakdown.table_taker_pts == 0


def _trick_won_by_south(card: Card) -> tuple[TrickCard, ...]:
    """Build a 4-card trick where South leads `card` and partner/defenders dump filler.

    Used by boss-modifier tests that need a valid trick where South wins.
    """
    # South leads the card under test (trump=HEARTS in callers, so a SPADES lead
    # gets followed by SPADES from N/E/W with lower ranks; South wins).
    return (
        TrickCard(Seat.SOUTH, card),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
    )


def test_boss_kings_zero():
    """2. Boss: Kings Zero - Verify Kings score 0 points."""
    # South captures four Kings of Spades across four tricks (one per suit-rank
    # combo would normally be impossible; we just need the kings_zero rule to
    # zero out card points for tricks containing kings).
    king_tricks = tuple(
        _trick_won_by_south(Card(Suit.SPADES, Rank.KING)) for _ in range(4)
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(kings_zero=True),
        completed_tricks=king_tricks,
    )
    breakdown = score_round(state)
    # Without boss: 4 kings = 4×4 = 16 + filler. With kings_zero: kings drop to 0.
    assert breakdown.table_taker_pts == 0


def test_boss_tens_zero():
    """3. Boss: Tens Zero - Verify Tens score 0 points."""
    ten_tricks = tuple(
        _trick_won_by_south(Card(Suit.SPADES, Rank.TEN)) for _ in range(4)
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(tens_zero=True),
        completed_tricks=ten_tricks,
    )
    breakdown = score_round(state)
    # Without boss: 4 tens = 4×10 = 40 + filler. With tens_zero: tens drop to 0.
    assert breakdown.table_taker_pts == 0


def test_boss_queen_spades_penalty():
    """6. Boss: Queen of Spades Penalty - Verify -25 points for QS."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(queen_spades_penalty=True),
        completed_tricks=tuple(
            [(TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.QUEEN)),
              TrickCard(Seat.NORTH, Card(Suit.CLUBS, Rank.SEVEN)),
              TrickCard(Seat.EAST, Card(Suit.CLUBS, Rank.EIGHT)),
              TrickCard(Seat.WEST, Card(Suit.CLUBS, Rank.NINE)))] +
            [(TrickCard(Seat.EAST, Card(Suit.DIAMONDS, Rank.ACE)),
              TrickCard(Seat.WEST, Card(Suit.DIAMONDS, Rank.TEN)),
              TrickCard(Seat.SOUTH, Card(Suit.DIAMONDS, Rank.KING)),
              TrickCard(Seat.NORTH, Card(Suit.DIAMONDS, Rank.QUEEN)))] * 7
        ),
        last_trick_winner=Seat.EAST
    )
    breakdown = score_round(state)
    assert any("Reine Noire" in m for m in breakdown.messages)
    # Taker Card points: QS (0) + 7 other tricks (0 because they lost them) = 0
    # Penalty -25. Result should be -25 or chute.
    assert breakdown.table_taker_pts < 0


def test_boss_invert_scoring():
    """9. Boss: Invert Scoring (La Malédiction) — winning more tricks zeroes you."""
    # Build 5 tricks NS wins, 3 tricks EW wins. Under invert_scoring,
    # NS won more tricks so taker_total should be zeroed out.
    ns_win = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),  # trump
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    ew_win = (
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.ACE)),  # trump, beats NS
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.QUEEN)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.TEN)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(invert_scoring=True),
        completed_tricks=tuple([ns_win] * 5 + [ew_win] * 3),
        last_trick_winner=Seat.EAST,
    )
    breakdown = score_round(state)
    # NS won 5 tricks > EW's 3 → invert_scoring zeroes NS total.
    assert breakdown.taker_total == 0
    assert any("Malédiction" in m for m in breakdown.messages)


# ── La Rupture: is_capot must honor Rupture in explicit-tricks branch ─────


def test_is_capot_honors_rupture_in_explicit_tricks_branch() -> None:
    """Live HUD CAPOT announcement (`gameflow.py` 8th-trick path) calls
    `is_capot(state, tricks=completed + [current])`. Pre-3.3.2 that branch
    re-derived winners with raw `trick_winner_seat`, ignoring La Rupture —
    so a raw NS sweep falsely shouted CAPOT mid-round while the final score
    correctly resolved as non-capot via `compute_trick_winners`. Lock the
    fix: both branches of `is_capot` must agree under La Rupture.
    """
    # Eight tricks where the raw winner is SOUTH every time. South leads
    # Spades (non-trump under trump=HEARTS); others follow with lower
    # Spades. Cross-trick rank uniqueness doesn't matter for winner
    # detection.
    def south_wins(lead_rank: Rank) -> tuple[TrickCard, ...]:
        return (
            TrickCard(Seat.SOUTH, Card(Suit.SPADES, lead_rank)),
            TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
            TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
            TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
        )

    high = [Rank.ACE, Rank.TEN, Rank.KING, Rank.QUEEN,
            Rank.JACK, Rank.ACE, Rank.TEN, Rank.KING]
    tricks = tuple(south_wins(r) for r in high)

    rupture_state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(no_consecutive_team_wins=True),
        completed_tricks=tricks,
    )

    # Default branch (tricks=None): already honored Rupture pre-3.3.2.
    assert is_capot(rupture_state) is None

    # Explicit-tricks branch: must also honor Rupture (the 3.3.2 fix).
    assert is_capot(rupture_state, tricks=list(tricks)) is None

    # Sanity: without Rupture, both branches see the raw NS sweep.
    no_rupture = replace(rupture_state, boss_modifiers=BossModifiers())
    assert is_capot(no_rupture) == 0
    assert is_capot(no_rupture, tricks=list(tricks)) == 0


# ── Anti-pattern lock (3.1.0 modifier_patch shim removal) ──────────────────


def test_invariant_no_underscore_boss_attrs() -> None:
    """Architecture-pinned anti-pattern: boss flags must be reached via
    `state.boss_modifiers.X`, NOT `getattr(state, "_X", False)`. After the
    underscore-shim removal in modifier_patch.py (3.1.0), no leading-underscore
    boss attribute should ever resolve on a vanilla GameState. Reading one
    indicates the foot-gun pattern has crept back into the codebase."""
    state = GameState(
        hands=((), (), (), ()),
        boss_modifiers=BossModifiers(no_belote=True, kings_zero=True),
    )

    for name in (
        "_no_belote",
        "_kings_zero",
        "_tens_zero",
        "_aces_zero",
        "_jacks_zero",
        "_ban_clubs",
        "_invert_scoring",
        "_no_dix_de_der",
    ):
        assert getattr(state, name, None) is None, (
            f"GameState resolved attribute {name!r} — the leading-underscore "
            "boss-flag access pattern is pinned against (see project memory). "
            "Read via state.boss_modifiers.<name> instead."
        )

    # And the canonical access path still works.
    assert state.boss_modifiers.no_belote is True
    assert state.boss_modifiers.kings_zero is True
