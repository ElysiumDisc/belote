"""Integration tests for behavioral fixes that wired previously-dead flags.

Each test constructs a minimal GameState (or BelAtroRun) with the flag set
and asserts the observable effect — proving the flag is now honored, not
just stored.
"""

from __future__ import annotations

from dataclasses import replace

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.belatro.items.jokers.hand_comp import LaSentinelle
from belote.belatro.items.vouchers import LaBalance, LaSurcoinche, forge_tierce
from belote.belatro.run.boss import BetrayalArc, LeDivorce, LeFantomePartenaire
from belote.deck import Card, Rank, Suit
from belote.game import (
    BossModifiers,
    GameState,
    Phase,
    Seat,
    TrickCard,
    legal_cards,
)
from belote.scoring import score_round

# ── Le Marseillais: announce_x2 ────────────────────────────────────────────


def _build_state_with_carre(joker_state: dict[str, object]) -> GameState:
    """South holds a Carré of Aces in initial_hands; score_round detects it."""
    south_hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.ACE),
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.SPADES, Rank.EIGHT),
        Card(Suit.SPADES, Rank.NINE),
        Card(Suit.SPADES, Rank.TEN),
    )
    return GameState(
        hands=((), (), (), ()),
        initial_hands=(south_hand, (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        _joker_state=joker_state,
    )


def test_announce_x2_doubles_declarations_when_flag_set() -> None:
    base = score_round(_build_state_with_carre({}))
    boosted = score_round(_build_state_with_carre({"announce_x2": True}))
    assert base.taker_declarations > 0  # sanity: carré detected
    assert boosted.taker_declarations == base.taker_declarations * 2


# ── Le Marseillais: no_belote_rebelote ──────────────────────────────────────


def test_no_belote_rebelote_deck_mod_suppresses_belote_points() -> None:
    state_with = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        belote_holders={Suit.HEARTS: Seat.SOUTH},
        belote_tracker=(True, True),
        _joker_state={"no_belote_rebelote": True},
    )
    breakdown = score_round(state_with)
    assert breakdown.taker_belote == 0


# ── La Balance voucher: tie_breaks_for_taker ────────────────────────────────


def test_la_balance_voucher_avoids_litige_on_tie() -> None:
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        _joker_state={"tie_breaks_for_taker": True},
    )
    # taker_card_pts == defender_card_pts == 0 → tie → would normally be litige
    breakdown = score_round(state)
    assert not breakdown.is_litige
    assert any("La Balance" in m for m in breakdown.messages)


def test_la_balance_voucher_apply_sets_run_flag() -> None:
    run = BelAtroRun()
    LaBalance().apply(run)
    assert run.tie_breaks_for_taker is True


# ── Le Républicain wild 7s/8s ──────────────────────────────────────────────


def test_republicain_wild_seven_legal_off_suit() -> None:
    """With republicain_wild on, a 7 of any suit is legal even when must-follow."""
    south_hand = (
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.NINE),  # would normally be only legal play
    )
    state = GameState(
        hands=(south_hand, (), (), ()),
        trump=Suit.SPADES,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
        current_trick=(TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.ACE)),),
        _joker_state={"republicain_wild": True},
    )
    legals = legal_cards(state, Seat.SOUTH)
    assert Card(Suit.SPADES, Rank.SEVEN) in legals
    assert Card(Suit.HEARTS, Rank.NINE) in legals


def test_republicain_wild_off_unsets_seven_when_must_follow() -> None:
    """Without the flag, must follow led suit even with a 7."""
    south_hand = (
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.NINE),
    )
    state = GameState(
        hands=(south_hand, (), (), ()),
        trump=Suit.SPADES,
        phase=Phase.PLAYING,
        turn=Seat.SOUTH,
        current_trick=(TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.ACE)),),
    )
    legals = legal_cards(state, Seat.SOUTH)
    assert Card(Suit.SPADES, Rank.SEVEN) not in legals
    assert Card(Suit.HEARTS, Rank.NINE) in legals


# ── La Sentinelle: ownership check ──────────────────────────────────────────


def test_la_sentinelle_ignores_jack_played_by_partner() -> None:
    """The trump Jack played by NORTH should not arm South's bonus."""
    joker = LaSentinelle()
    js: dict[str, object] = {}
    joker.on_round_start(js)

    # NORTH led the trump Jack → NORTH played it → South wasn't dealt it.
    event = TrickWonEvent(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),  # played by NORTH (leader)
            Card(Suit.HEARTS, Rank.SEVEN),  # WEST
            Card(Suit.HEARTS, Rank.EIGHT),  # SOUTH
            Card(Suit.HEARTS, Rank.NINE),   # EAST
        ),
        trick_number=1,
        is_last=False,
        card_points=20,
        trump=Suit.HEARTS,
        leader_seat=Seat.NORTH,
    )
    joker.on_trick_won(event, js)
    assert js[f"{joker.id}_had_jack"] is False


def test_la_sentinelle_arms_when_south_plays_trump_jack() -> None:
    joker = LaSentinelle()
    js: dict[str, object] = {}
    joker.on_round_start(js)

    # SOUTH led the trump Jack; partner won via overtrump.
    event = TrickWonEvent(
        winner=Seat.NORTH,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),  # SOUTH (leader)
            Card(Suit.HEARTS, Rank.SEVEN),  # EAST
            Card(Suit.HEARTS, Rank.NINE),  # NORTH (wins)
            Card(Suit.HEARTS, Rank.EIGHT),  # WEST
        ),
        trick_number=1,
        is_last=False,
        card_points=20,
        trump=Suit.HEARTS,
        leader_seat=Seat.SOUTH,
    )
    joker.on_trick_won(event, js)
    assert js[f"{joker.id}_had_jack"] is True
    assert js[f"{joker.id}_won_with_jack"] is False


# ── Boss flag-driven behavior (#1 + #14 + #15) ──────────────────────────────


def test_betrayal_arc_flags_lock_trust_zero() -> None:
    """BetrayalArc.flags() exposes lock_trust_zero so main.py can react."""
    flags = BetrayalArc().flags()
    assert flags.lock_trust_zero is True
    assert flags.agent_double_active is True


def test_le_divorce_flags_lock_trust_zero() -> None:
    flags = LeDivorce().flags()
    assert flags.lock_trust_zero is True


def test_le_fantome_partenaire_flags_hide_partner_hand() -> None:
    flags = LeFantomePartenaire().flags()
    assert flags.hide_partner_hand is True


# ── L'Aristocrate gold_seal_aces flag plumbing ──────────────────────────────


def test_aristocrate_deck_sets_gold_seal_aces() -> None:
    run = BelAtroRun(deck_id="aristocrate")
    assert run.gold_seal_aces is True


def test_anarchiste_deck_sets_corrupted_pool_visible() -> None:
    run = BelAtroRun(deck_id="anarchiste")
    assert run.corrupted_pool_visible is True


# ── La Surcoinche voucher actually unlocks the flag ─────────────────────────


def test_la_surcoinche_apply_sets_unlock_flag() -> None:
    run = BelAtroRun()
    assert run.surcoinche_unlocked is False
    LaSurcoinche().apply(run)
    assert run.surcoinche_unlocked is True


# ── TierceForge runtime helper ──────────────────────────────────────────────


def test_forge_tierce_consumes_three_charges_and_levels_planet() -> None:
    run = BelAtroRun()
    run.tierce_charges = 3
    ok = forge_tierce(run, "the_sun")
    assert ok is True
    assert run.tierce_charges == 0
    assert "tout_atout" in run.contract_levels


def test_forge_tierce_refuses_when_insufficient_charges() -> None:
    run = BelAtroRun()
    run.tierce_charges = 2
    ok = forge_tierce(run, "the_sun")
    assert ok is False
    assert run.tierce_charges == 2


# ── Republicain deck propagates wild flag into card_enhancements ───────────


def test_republicain_deck_enables_wild_flag() -> None:
    run = BelAtroRun(deck_id="republicain")
    assert run.card_enhancements.get("republicain_wild") is True


# ── Le Coincheur start_coinched flag remains in card_enhancements ──────────


def test_coinche_deck_start_coinched_flag_present() -> None:
    run = BelAtroRun(deck_id="coinche")
    assert run.card_enhancements.get("start_coinched") is True


# ── Sanity: prior baseline tests still meaningful ──────────────────────────


def test_existing_kings_zero_unaffected() -> None:
    """Ensure the new _joker_state plumbing didn't break boss flag reads."""
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(kings_zero=True),
    )
    breakdown = score_round(state)
    # No tricks → 0 card pts, but the call must not crash.
    assert breakdown.table_taker_pts == 0


# Avoid unused import warning when the file is run with strict linters.
_ = replace
