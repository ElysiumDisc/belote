"""4.5.0 Conditional Engine jokers.

Six jokers landing in 4.5.0:
- LeCavalierNoir (trick_timing): spade-on-heart-lead win → ×3 mult
- LArcEnCiel (trick_timing): NS trick whose winner suit ≠ lead suit → +2 mult
- LeCollectionneur (annonces): NS Annonce card played in trick 2+ → +$2/+5 mult per card
- LeMathematicien (annonces): NS Annonce score % 5 == 0 → ×2 mult
- LEclat (annonces): trump K/Q in NS-won trick → triple chips for that trick
- LePreteur (economy): on round_start, $0→+$15; $50+→ -$5 +×1.2 mult

Joker pattern test: one happy-path + one non-trigger per joker, mirroring
`tests/belatro/test_partner_jokers.py`.
"""

from __future__ import annotations

from typing import Any

from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import (
    DeclarationScoredEvent,
    TrickWonEvent,
)
from belote.belatro.items.jokers.annonces import (
    LEclat,
    LeCollectionneur,
    LeMathematicien,
)
from belote.belatro.items.jokers.economy import LePreteur
from belote.belatro.items.jokers.trick_timing import LArcEnCiel, LeCavalierNoir
from belote.deck import Card, Rank, Suit
from belote.game import Declaration, GameState, Seat, Sequence

# ── LeCavalierNoir ──────────────────────────────────────────────────────────


def _trick(
    winner: Seat,
    cards: tuple[Card, ...],
    *,
    trump: Suit | None = Suit.SPADES,
    leader: Seat = Seat.SOUTH,
    trick_number: int = 2,
    card_points: int = 20,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=False,
        card_points=card_points,
        trump=trump,
        leader_seat=leader,
    )


def test_le_cavalier_noir_fires_on_spade_over_heart_lead() -> None:
    j = LeCavalierNoir()
    # SOUTH leads ♥A, EAST ♥7, NORTH wins with ♠J (spade over heart lead).
    evt = _trick(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.HEARTS, Rank.ACE),
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.SPADES, Rank.JACK),
            Card(Suit.HEARTS, Rank.EIGHT),
        ),
    )
    res = j.on_trick_won(evt, {})
    assert res is not None and res.times_mult == 3.0


def test_le_cavalier_noir_silent_on_diamond_lead() -> None:
    j = LeCavalierNoir()
    evt = _trick(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.DIAMONDS, Rank.ACE),
            Card(Suit.DIAMONDS, Rank.SEVEN),
            Card(Suit.SPADES, Rank.JACK),
            Card(Suit.DIAMONDS, Rank.EIGHT),
        ),
    )
    assert j.on_trick_won(evt, {}) is None


def test_le_cavalier_noir_silent_when_ew_wins() -> None:
    j = LeCavalierNoir()
    evt = _trick(
        winner=Seat.EAST,
        cards=(
            Card(Suit.HEARTS, Rank.ACE),
            Card(Suit.SPADES, Rank.JACK),  # EAST wins
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.SEVEN),
        ),
    )
    assert j.on_trick_won(evt, {}) is None


# ── LArcEnCiel ──────────────────────────────────────────────────────────────


def test_arc_en_ciel_fires_on_cross_suit_ns_win() -> None:
    """Spade trump wins on heart lead → +2 mult."""
    j = LArcEnCiel()
    evt = _trick(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.SPADES, Rank.JACK),  # SOUTH? wait, leader was SOUTH (idx 0)
        ),
        leader=Seat.EAST,  # so SOUTH plays last (idx 3)
    )
    res = j.on_trick_won(evt, {})
    assert res is not None and res.add_mult == 2.0


def test_arc_en_ciel_silent_on_same_suit_win() -> None:
    j = LArcEnCiel()
    evt = _trick(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.SEVEN),  # SOUTH
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.ACE),
        ),
    )
    # SOUTH led with the Ace? No — SOUTH led with 7, but they won with the Ace.
    # Wait — SOUTH is leader (idx 0), so SOUTH played the 7 first. Winner is
    # SOUTH per the test setup, but the 7 doesn't beat an Ace. This event is
    # a bit synthetic, but the joker only cares about (winner's card suit) vs
    # (lead suit); both are HEARTS here, so no bonus.
    assert j.on_trick_won(evt, {}) is None


# ── LeCollectionneur ────────────────────────────────────────────────────────


def _state_with_tierce_in_hearts() -> GameState:
    seq = Sequence(
        length=3,
        top_rank=10,
        suit=Suit.HEARTS,
        is_trump=True,
        cards=(
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.JACK),
        ),
    )
    decl = Declaration(seat=Seat.SOUTH, kind="sequence", detail=seq)
    return GameState(hands=((), (), (), ()), declarations=(decl,))


def test_collectionneur_pays_per_annonce_card_in_late_trick() -> None:
    """SOUTH plays J♥ (an annonce card) in trick 3 → +$2, +5 mult for that one card."""
    j = LeCollectionneur()
    acc = ScoreAccumulator()
    acc.attach_jokers([j])
    state = _state_with_tierce_in_hearts()
    # Declaration scores first to populate `_ns_annonce_cards`.
    state = acc.update_state(
        state, DeclarationScoredEvent(Seat.SOUTH, "Tierce", 20)
    )
    assert "_ns_annonce_cards" in state._joker_state

    # Trick 3 contains the J♥ played by SOUTH (the leader).
    state_after = acc.update_state(
        state,
        _trick(
            winner=Seat.SOUTH,
            cards=(
                Card(Suit.HEARTS, Rank.JACK),    # SOUTH — annonce card
                Card(Suit.HEARTS, Rank.SEVEN),
                Card(Suit.HEARTS, Rank.EIGHT),
                Card(Suit.HEARTS, Rank.QUEEN),
            ),
            trump=Suit.HEARTS,
            leader=Seat.SOUTH,
            trick_number=3,
        ),
    )
    # +5 mult (1 + 5 = 6) and +$2.
    assert state_after._mult == 6.0
    assert state_after._bonus_money == 2


def test_collectionneur_silent_on_trick_1() -> None:
    j = LeCollectionneur()
    state: dict[str, Any] = {
        "_ns_annonce_cards": frozenset({("HEARTS", "JACK")}),
    }
    evt = _trick(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.QUEEN),
        ),
        trick_number=1,
    )
    assert j.on_trick_won(evt, state) is None


# ── LeMathematicien ─────────────────────────────────────────────────────────


def test_mathematicien_fires_on_multiple_of_5_annonce() -> None:
    j = LeMathematicien()
    res = j.on_declaration(
        DeclarationScoredEvent(Seat.SOUTH, "Tierce", 20), {}
    )
    assert res is not None and res.times_mult == 2.0


def test_mathematicien_silent_on_ew_annonce() -> None:
    j = LeMathematicien()
    assert (
        j.on_declaration(DeclarationScoredEvent(Seat.EAST, "Tierce", 20), {})
        is None
    )


def test_mathematicien_silent_on_zero_points() -> None:
    """Defensive: 0 % 5 == 0 mathematically but a no-op declaration shouldn't pay."""
    j = LeMathematicien()
    assert (
        j.on_declaration(DeclarationScoredEvent(Seat.SOUTH, "Tierce", 0), {})
        is None
    )


# ── LEclat ──────────────────────────────────────────────────────────────────


def test_eclat_triples_chips_when_belote_in_won_trick() -> None:
    """A trick won by NS that contains the trump K or Q gets +2× its base
    chip contribution (so total = 3× the trick's card_points)."""
    j = LEclat()
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.KING),     # the belote half — trump K
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
        ),
        trick_number=2,
        is_last=False,
        card_points=18,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    res = j.on_trick_won(evt, {})
    assert res is not None and res.add_chips == 36  # 2 × 18


def test_eclat_silent_without_belote_in_trick() -> None:
    j = LEclat()
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(
            Card(Suit.HEARTS, Rank.ACE),
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
        ),
        trick_number=2,
        is_last=False,
        card_points=11,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    assert j.on_trick_won(evt, {}) is None


# ── LePreteur ───────────────────────────────────────────────────────────────


def test_preteur_pays_15_when_broke() -> None:
    j = LePreteur()
    res = j.on_round_start({"current_money": 0})
    assert res is not None and res.add_money == 15
    assert res.times_mult == 0  # default — no mult component when broke-bailout fires


def test_preteur_skims_5_for_120_mult_when_rich() -> None:
    j = LePreteur()
    res = j.on_round_start({"current_money": 60})
    assert res is not None
    assert res.add_money == -5
    assert res.times_mult == 1.2


def test_preteur_silent_in_middle_band() -> None:
    j = LePreteur()
    assert j.on_round_start({"current_money": 25}) is None


def test_preteur_round_start_result_lands_on_accumulator() -> None:
    """4.5.0 plumbing fix: ScoreAccumulator.trigger_round_start now applies
    JokerResult returns from on_round_start (previously discarded). Without
    this, LePrêteur's $15 would never reach the wallet."""
    j = LePreteur()
    acc = ScoreAccumulator()
    acc.attach_jokers([j])
    state = GameState(hands=((), (), (), ()), _joker_state={"current_money": 0})
    out = acc.trigger_round_start(state)
    assert out._bonus_money == 15


def test_preteur_skim_actually_debits_economy() -> None:
    """4.6.5 regression: pre-fix, the round-end payout site in belatro/main.py
    only credited `_bonus_money` if it was > 0, silently dropping LePreteur's
    -$5 skim cost while still applying ×1.2 mult. The negative branch now
    routes through `Economy.spend_money`, matching the joker's stated cost."""
    from belote.belatro.core.economy import Economy

    j = LePreteur()
    acc = ScoreAccumulator()
    acc.attach_jokers([j])
    state = GameState(hands=((), (), (), ()), _joker_state={"current_money": 60})
    out = acc.trigger_round_start(state)
    assert out._bonus_money == -5

    economy = Economy(money=60)
    # Replicate belatro/main.py:453-461 payout dispatch.
    bonus = out._bonus_money
    if bonus > 0:
        economy.add_money(bonus)
    elif bonus < 0:
        economy.spend_money(-bonus)
    assert economy.money == 55, "LePreteur's $5 skim must actually debit wallet"


# ── Registry ────────────────────────────────────────────────────────────────


def test_phase_4_5_jokers_registered() -> None:
    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()
    assert "le_cavalier_noir" in registry.jokers
    assert "l_arc_en_ciel" in registry.jokers
    assert "le_collectionneur" in registry.jokers
    assert "le_mathematicien" in registry.jokers
    assert "l_eclat" in registry.jokers
    assert "le_preteur" in registry.jokers
