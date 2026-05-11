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


def test_la_sentinelle_arms_when_partner_plays_trump_jack() -> None:
    """3.2.0: La Sentinelle arms for the NS *team*, not just South.

    Pre-3.2 the joker only fired when South personally was dealt the trump
    Jack, ignoring North (the partner) entirely. Belote is a team game and
    'you' in the joker's description means the NS team, so a trump Jack
    held by North must also arm the bonus."""
    joker = LaSentinelle()
    js: dict[str, object] = {}
    joker.on_round_start(js)

    # NORTH led the trump Jack → NORTH played it from their hand.
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
    # NS team was dealt the trump Jack (via North), so had_jack flips.
    assert js[f"{joker.id}_had_jack"] is True
    # NORTH (team NS) also won the trick → team won with the Jack.
    assert js[f"{joker.id}_won_with_jack"] is True


def test_la_sentinelle_does_not_arm_for_opponent_jack() -> None:
    """When an EW seat is dealt the trump Jack, NS's joker must not arm."""
    joker = LaSentinelle()
    js: dict[str, object] = {}
    joker.on_round_start(js)

    # EAST led the trump Jack.
    event = TrickWonEvent(
        winner=Seat.EAST,
        cards=(
            Card(Suit.HEARTS, Rank.JACK),  # EAST (leader)
            Card(Suit.HEARTS, Rank.SEVEN),  # NORTH
            Card(Suit.HEARTS, Rank.EIGHT),  # WEST
            Card(Suit.HEARTS, Rank.NINE),   # SOUTH
        ),
        trick_number=1,
        is_last=False,
        card_points=20,
        trump=Suit.HEARTS,
        leader_seat=Seat.EAST,
    )
    joker.on_trick_won(event, js)
    assert js[f"{joker.id}_had_jack"] is False
    assert js[f"{joker.id}_won_with_jack"] is False


def test_la_sentinelle_arms_when_south_plays_trump_jack() -> None:
    joker = LaSentinelle()
    js: dict[str, object] = {}
    joker.on_round_start(js)

    # SOUTH led the trump Jack; partner (NORTH) won via overtrump.
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
    # 3.2.0: NORTH winning the trick is a team-NS win, so won_with_jack
    # is True (pre-3.2 this was False because the check was Seat.SOUTH only).
    assert js[f"{joker.id}_won_with_jack"] is True


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


def test_ai_memory_respects_hide_partner_hand() -> None:
    """C1: when `hide_partner_hand` is set, `AIMemory.update_memory` must
    refuse to populate `partner_hand` even though partner's cards are
    present in `state.hands`. Without this gate the AI cheats the boss
    flag — the human is blinded but the AI plays with perfect info."""
    from belote.ai import AIPlayer, Difficulty

    north_hand = (
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
    )
    state = GameState(
        hands=((), (), north_hand, ()),
        phase=Phase.PLAYING,
        trump=Suit.HEARTS,
        boss_modifiers=BossModifiers(hide_partner_hand=True),
    )
    ai = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    ai.update_memory(state)
    assert ai.memory.partner_hand == set()

    # Sanity: without the flag the same call DOES populate partner_hand.
    state_no_flag = replace(state, boss_modifiers=BossModifiers())
    ai2 = AIPlayer(Seat.SOUTH, Difficulty.HARD)
    ai2.update_memory(state_no_flag)
    assert ai2.memory.partner_hand == set(north_hand)


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


# ── 3.0.0: The Sun planet (Tout Atout +Mult/trick beyond 4th) ─────────────


def test_the_sun_adds_mult_after_fourth_trick() -> None:
    """Sun bonus_mult_per_trick fires only on Tout Atout, only after trick 4."""
    from belote.belatro.core.scoring import ScoreAccumulator

    acc = ScoreAccumulator(contract_levels={"tout_atout": {"bonus_mult_per_trick": 1.0}})
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.TOUT_ATOUT,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    # Trick #4 — should NOT add Sun mult (only beyond the 4th).
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=4,
            is_last=False,
            card_points=0,
            trump=Suit.TOUT_ATOUT,
        ),
    )
    mult_after_t4 = state._mult
    # Trick #5 — should add +1.0 mult.
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=5,
            is_last=False,
            card_points=0,
            trump=Suit.TOUT_ATOUT,
        ),
    )
    assert state._mult == mult_after_t4 + 1.0


def test_the_sun_inactive_outside_tout_atout() -> None:
    """Sun must not apply when contract is normal trump."""
    from belote.belatro.core.scoring import ScoreAccumulator

    acc = ScoreAccumulator(contract_levels={"tout_atout": {"bonus_mult_per_trick": 1.0}})
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    initial_mult = state._mult
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=5,
            is_last=False,
            card_points=20,
            trump=Suit.HEARTS,
        ),
    )
    assert state._mult == initial_mult


# ── 3.0.0: Libra planet (Coinche +Mult on success) ────────────────────────


def test_libra_adds_mult_on_coinche_win() -> None:
    """Libra coinche_multiplier fires on coinche-level >0 successful round."""
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import RoundEndEvent

    acc = ScoreAccumulator(contract_levels={"coinche": {"coinche_multiplier": 1.0}})
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
    )

    class _BD:
        is_failed = False

    initial_mult = state._mult
    state = acc.update_state(
        state,
        RoundEndEvent(
            breakdown=_BD(),
            taker_seat=Seat.SOUTH,
            trump=Suit.HEARTS,
            capot=False,
            contract="coinche",
            coinche_level=1,
        ),
    )
    assert state._mult == initial_mult + 1.0


def test_libra_skips_failed_coinche() -> None:
    """A failed coinche round must not pay Libra mult."""
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import RoundEndEvent

    acc = ScoreAccumulator(contract_levels={"coinche": {"coinche_multiplier": 1.0}})
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
    )

    class _BD:
        is_failed = True

    initial_mult = state._mult
    state = acc.update_state(
        state,
        RoundEndEvent(
            breakdown=_BD(),
            taker_seat=Seat.SOUTH,
            trump=Suit.HEARTS,
            capot=False,
            contract="coinche",
            coinche_level=1,
        ),
    )
    assert state._mult == initial_mult


# Avoid unused import warning when the file is run with strict linters.
_ = replace


# ── 3.0.0: Joker editions (Foil/Holo/Polychrome/Negative) ─────────────────


def test_foil_edition_adds_50_chips_per_trigger() -> None:
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import TrickWonEvent
    from belote.belatro.items.base import Edition, Joker, JokerResult, Rarity

    class _AlwaysTrigger(Joker):
        id = "alwaystrigger"
        name = "Always"
        description = "Test joker"
        cost = 0
        rarity = Rarity.COMMON

        def on_trick_won(self, event, state):
            return JokerResult(add_chips=10)

    j = _AlwaysTrigger()
    j.edition = Edition.FOIL
    acc = ScoreAccumulator()
    acc.attach_jokers([j])

    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    initial_chips = state._chips
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=1,
            is_last=False,
            card_points=0,
            trump=Suit.HEARTS,
        ),
    )
    # Base trick chips: 0 raw + 10 joker + 50 foil = 60.
    assert state._chips == initial_chips + 60


def test_holo_edition_adds_10_mult_per_trigger() -> None:
    """3.0.1: HOLO edition adds +10 Mult on every successful joker trigger."""
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import TrickWonEvent
    from belote.belatro.items.base import Edition, Joker, JokerResult, Rarity

    class _AlwaysTrigger(Joker):
        id = "holotrigger"
        name = "Holo"
        description = "Test joker"
        cost = 0
        rarity = Rarity.COMMON

        def on_trick_won(self, event, state):
            return JokerResult(add_mult=2.0)

    j = _AlwaysTrigger()
    j.edition = Edition.HOLO
    acc = ScoreAccumulator()
    acc.attach_jokers([j])

    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    initial_mult = state._mult
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=1,
            is_last=False,
            card_points=0,
            trump=Suit.HEARTS,
        ),
    )
    # Base joker mult +2.0 then HOLO adds +10.0 → +12.0 total.
    assert state._mult == initial_mult + 12.0


def test_polychrome_edition_multiplies_mult_by_1_5() -> None:
    """3.0.1: POLYCHROME edition applies ×1.5 mult on every successful trigger."""
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import TrickWonEvent
    from belote.belatro.items.base import Edition, Joker, JokerResult, Rarity

    class _AlwaysTrigger(Joker):
        id = "polytrigger"
        name = "Poly"
        description = "Test joker"
        cost = 0
        rarity = Rarity.COMMON

        def on_trick_won(self, event, state):
            return JokerResult(add_mult=2.0)

    j = _AlwaysTrigger()
    j.edition = Edition.POLYCHROME
    acc = ScoreAccumulator()
    acc.attach_jokers([j])

    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.PLAYING,
    )
    initial_mult = state._mult
    state = acc.update_state(
        state,
        TrickWonEvent(
            winner=Seat.SOUTH,
            cards=(Card(Suit.HEARTS, Rank.JACK),),
            trick_number=1,
            is_last=False,
            card_points=0,
            trump=Suit.HEARTS,
        ),
    )
    # Joker adds +2.0 mult; POLYCHROME applies ×1.5 to current mult AFTER the
    # add. So: (initial + 2.0) × 1.5.
    assert state._mult == (initial_mult + 2.0) * 1.5


def test_negative_edition_grants_extra_slot_at_purchase() -> None:
    """Buying a Negative joker should grow run.joker_slots by 1 instead of
    consuming an existing slot."""
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.items.base import Edition, Joker, Rarity
    from belote.belatro.run.shop import Shop

    class _DummyJ(Joker):
        id = "dummy"
        name = "Dummy"
        description = "test"
        cost = 0
        rarity = Rarity.COMMON

    run = BelAtroRun()
    initial_slots = run.joker_slots
    initial_jokers = len(run.jokers)
    shop = Shop(run)
    j = _DummyJ()
    j.edition = Edition.NEGATIVE
    shop._apply_item(j)
    assert run.joker_slots == initial_slots + 1
    assert len(run.jokers) == initial_jokers + 1


# ── 3.0.0: New boss blinds (Le Sauvage / L'Iconoclaste / Le Mime) ─────────


def test_aces_zero_boss_zeros_ace_card_points() -> None:
    """Le Sauvage: ace points stripped from card-point sum."""
    south_hand = (
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.SPADES, Rank.SEVEN),
    )
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=(south_hand, (), (), ()),
        trump=Suit.SPADES,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(trick,),
        last_trick_winner=Seat.SOUTH,
        boss_modifiers=BossModifiers(aces_zero=True),
    )
    breakdown = score_round(state)
    # Card-pts only: A=0 (zeroed), 7/8/9 of non-trump = 0 → 0.
    # table_taker_pts also folds in the +10 dix-de-der bonus, so total = 10.
    # Compare to a no-flag baseline to prove the ace was actually zeroed:
    no_flag_state = replace(state, boss_modifiers=BossModifiers())
    baseline = score_round(no_flag_state)
    assert breakdown.table_taker_pts < baseline.table_taker_pts


def test_jacks_zero_boss_zeros_jack_card_points() -> None:
    """L'Iconoclaste: Jack of trump (normally 20) zeroed."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),  # trump Jack = 20 normally
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(trick,),
        last_trick_winner=Seat.SOUTH,
        boss_modifiers=BossModifiers(jacks_zero=True),
    )
    breakdown = score_round(state)
    # Trump-9 = 14; J zeroed = 0; 7,8 = 0. Trick = 14, plus +10 dix-de-der = 24.
    assert breakdown.table_taker_pts == 24
    # Without the flag the trump Jack would add 20 → 14+20+10 = 44.
    no_flag = score_round(replace(state, boss_modifiers=BossModifiers()))
    assert no_flag.table_taker_pts == 44


def test_declarations_zero_boss_zeros_carre() -> None:
    """Le Mime: Carré of Aces (200 pts) becomes 0."""
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
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=(south_hand, (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        boss_modifiers=BossModifiers(declarations_zero=True),
    )
    breakdown = score_round(state)
    assert breakdown.taker_declarations == 0


def test_three_new_bosses_in_registry() -> None:
    from belote.belatro.run.boss import (
        ALL_BOSS_MODIFIERS,
        LeMime,
        LeSauvage,
        LIconoclaste,
    )
    assert LeSauvage in ALL_BOSS_MODIFIERS
    assert LIconoclaste in ALL_BOSS_MODIFIERS
    assert LeMime in ALL_BOSS_MODIFIERS


def test_le_mime_flags_declarations_zero() -> None:
    from belote.belatro.run.boss import LeMime
    flags = LeMime().flags()
    assert flags.declarations_zero is True


# ── 3.0.1: separate_scoring × zero-flag composition ───────────────────────


def test_separate_scoring_with_aces_zero_zeroes_aces_in_per_seat_path() -> None:
    """When La Compétition + Le Sauvage are both active, per-seat scoring
    must also zero Aces — not just the normal scoring path."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.SPADES, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(trick,),
        last_trick_winner=Seat.SOUTH,
        contract="hearts",
        boss_modifiers=BossModifiers(separate_scoring=True, aces_zero=True),
    )
    breakdown = score_round(state)
    no_flag = score_round(replace(state, boss_modifiers=BossModifiers(separate_scoring=True)))
    # With aces_zero, the per-seat path must produce a strictly smaller pts total.
    assert breakdown.table_taker_pts < no_flag.table_taker_pts


def test_separate_scoring_with_jacks_zero_zeroes_jacks_in_per_seat_path() -> None:
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.JACK)),  # trump J = 20
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.SEVEN)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.EIGHT)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(trick,),
        last_trick_winner=Seat.SOUTH,
        contract="hearts",
        boss_modifiers=BossModifiers(separate_scoring=True, jacks_zero=True),
    )
    breakdown = score_round(state)
    no_flag = score_round(replace(state, boss_modifiers=BossModifiers(separate_scoring=True)))
    assert breakdown.table_taker_pts < no_flag.table_taker_pts


def test_aces_zero_plus_kings_zero_plus_jacks_zero_compose() -> None:
    """All three rank-zero flags simultaneously must compose without bug."""
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.WEST, Card(Suit.HEARTS, Rank.KING)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.JACK)),
        TrickCard(Seat.EAST, Card(Suit.HEARTS, Rank.NINE)),
    )
    state = GameState(
        hands=((), (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        completed_tricks=(trick,),
        last_trick_winner=Seat.SOUTH,
        boss_modifiers=BossModifiers(aces_zero=True, kings_zero=True, jacks_zero=True),
    )
    breakdown = score_round(state)
    # Trump-9 = 14; A/K/J zeroed; +10 dix-de-der = 24 total.
    assert breakdown.table_taker_pts == 24


def test_declarations_zero_with_separate_scoring_no_double_count() -> None:
    """Le Mime + La Compétition: separate_scoring already zeros declarations.
    Adding declarations_zero on top must remain stable (no double-zero,
    no negative values)."""
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
    state = GameState(
        hands=((), (), (), ()),
        initial_hands=(south_hand, (), (), ()),
        trump=Suit.HEARTS,
        taker=Seat.SOUTH,
        phase=Phase.SCORING,
        contract="hearts",
        boss_modifiers=BossModifiers(separate_scoring=True, declarations_zero=True),
    )
    breakdown = score_round(state)
    assert breakdown.taker_declarations == 0
