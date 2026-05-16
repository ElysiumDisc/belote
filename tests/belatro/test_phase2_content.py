"""Phase 2 content tests: contract jokers, annonce jokers, capot insurance,
trust tier scaling, betrayal boss, new decks/tarots."""

from __future__ import annotations

from typing import Any

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.engine.event_bus import (
    BeloteAnnouncedEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)
from belote.belatro.items.base import Joker, JokerResult, Rarity
from belote.belatro.items.jokers.annonces import (
    QuinteRoyale,
    RebeloteEcho,
    TierceCharger,
)
from belote.belatro.items.jokers.coinche import CoincheStack, ToutStreak
from belote.belatro.items.tarots import LaMaisonDieu, LeDiable
from belote.belatro.items.vouchers import CapotInsurance, TierceForge
from belote.belatro.partner.trust import TrustTrack
from belote.belatro.run.boss import ALL_BOSS_MODIFIERS, BetrayalArc
from belote.belatro.run.decks import STARTING_DECKS
from belote.deck import Suit
from belote.game import GameState, Seat

# ── Coinche jokers ─────────────────────────────────────────────────────────


class _StubBreakdown:
    is_failed = False


class _FailedBreakdown:
    is_failed = True


def _round_end(
    coinche_level: int = 0,
    trump: Suit | None = Suit.HEARTS,
    failed: bool = False,
) -> RoundEndEvent:
    return RoundEndEvent(
        breakdown=_FailedBreakdown() if failed else _StubBreakdown(),
        taker_seat=Seat.SOUTH,
        trump=trump,
        capot=False,
        contract="normal",
        coinche_level=coinche_level,
    )


# ── 3.9.3 R4: LeBanquier suppresses bonus on chute ──────────────────────────


def test_le_banquier_pays_nothing_when_round_failed() -> None:
    """3.9.3 R4 regression: LeBanquier's description says 'Earn $1 for every
    10 card points you score above the Blind target'. Pre-3.9.3 the joker
    paid out unconditionally — even on chute, where points 'scored' don't
    reflect a successful contract. The fix gates on `breakdown.is_failed`.
    """
    from belote.belatro.items.jokers.economy import LeBanquier

    class _FailedBdHigh:
        is_failed = True
        taker_total = 200  # would have been $12 of bonus pre-3.9.3
        defender_total = 100

    event = RoundEndEvent(
        breakdown=_FailedBdHigh(),
        taker_seat=Seat.SOUTH,
        trump=Suit.HEARTS,
        capot=False,
    )
    result = LeBanquier().on_round_end(event, {"target_score": 80})
    assert result is None, "LeBanquier must not pay out on a failed round"


def test_le_banquier_pays_only_when_ns_was_taker() -> None:
    """LeBanquier's 'score above target' framing only makes sense for the
    taker team — defender chute totals shouldn't trigger the bonus."""
    from belote.belatro.items.jokers.economy import LeBanquier

    class _OkBd:
        is_failed = False
        taker_total = 200
        defender_total = 200

    # EW is taker → LeBanquier on NS side gets no bonus.
    event = RoundEndEvent(
        breakdown=_OkBd(),
        taker_seat=Seat.EAST,
        trump=Suit.HEARTS,
        capot=False,
    )
    result = LeBanquier().on_round_end(event, {"target_score": 80})
    assert result is None


def test_le_banquier_pays_on_ns_win() -> None:
    """Happy path unchanged: NS taker, contract held, points above target."""
    from belote.belatro.items.jokers.economy import LeBanquier

    class _OkBd:
        is_failed = False
        taker_total = 150  # 70 above an 80 threshold → $7
        defender_total = 50

    event = RoundEndEvent(
        breakdown=_OkBd(),
        taker_seat=Seat.SOUTH,
        trump=Suit.HEARTS,
        capot=False,
    )
    result = LeBanquier().on_round_end(event, {"target_score": 80})
    assert result is not None
    assert result.add_money == 7


def test_coinche_stack_only_fires_when_coinched_and_won() -> None:
    j = CoincheStack()
    assert j.on_round_end(_round_end(coinche_level=0), {}) is None
    assert j.on_round_end(_round_end(coinche_level=1, failed=True), {}) is None
    res = j.on_round_end(_round_end(coinche_level=1), {})
    assert res is not None and res.add_mult == 4.0
    res2 = j.on_round_end(_round_end(coinche_level=2), {})
    assert res2 is not None and res2.add_mult == 8.0


def test_tout_streak_resets_on_break() -> None:
    j = ToutStreak()
    state: dict[str, Any] = {}
    # Three wins in a row
    for _ in range(3):
        j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    assert state[f"{j.id}_streak"] == 3
    # A failed Tout Atout breaks the streak
    j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT, failed=True), state)
    assert state[f"{j.id}_streak"] == 0
    # Non-Tout rounds neither advance nor reset
    state[f"{j.id}_streak"] = 5
    j.on_round_end(_round_end(trump=Suit.HEARTS), state)
    assert state[f"{j.id}_streak"] == 5


def test_tout_streak_times_mult_grows() -> None:
    j = ToutStreak()
    state: dict[str, Any] = {}
    res1 = j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    res2 = j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    res3 = j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    assert res1 is not None and res1.times_mult == 1.5
    assert res2 is not None and res2.times_mult == 2.0
    assert res3 is not None and res3.times_mult == 2.5


# ── Annonce jokers ─────────────────────────────────────────────────────────


def test_tierce_charger_increments_state_and_pays_chips() -> None:
    j = TierceCharger()
    state: dict[str, Any] = {}
    res = j.on_declaration(
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=20),
        state,
    )
    assert res is not None and res.add_chips == 5
    assert state["_pending_tierce_charge"] == 1


def test_tierce_charger_skips_non_ns() -> None:
    j = TierceCharger()
    state: dict[str, Any] = {}
    assert (
        j.on_declaration(
            DeclarationScoredEvent(seat=Seat.EAST, declaration_type="sequence", points=20),
            state,
        )
        is None
    )
    assert "_pending_tierce_charge" not in state


def test_rebelote_echo_only_on_rebelote() -> None:
    j = RebeloteEcho()
    assert (
        j.on_belote(BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False), {})
        is None
    )
    res = j.on_belote(BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True), {})
    assert res is not None and res.times_mult == 3.0


def test_quinte_royale_legendary_arms_and_fires() -> None:
    j = QuinteRoyale()
    assert j.rarity == Rarity.LEGENDARY
    state: dict[str, Any] = {}
    j.on_declaration(
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=100),
        state,
    )
    assert state[f"{j.id}_armed"] is True
    res = j.on_round_end(_round_end(), state)
    assert res is not None and res.times_mult == 4.0
    # Armed flag is consumed
    assert f"{j.id}_armed" not in state


# ── Capot Insurance / Tierce Forge ─────────────────────────────────────────


def test_capot_insurance_voucher_sets_flag() -> None:
    run = BelAtroRun()
    assert run.capot_insurance is False
    CapotInsurance().apply(run)
    assert run.capot_insurance is True


def test_tierce_forge_voucher_apply_is_noop_at_apply_time() -> None:
    run = BelAtroRun()
    # Just verify it doesn't crash; the spend logic lives in the shop.
    TierceForge().apply(run)
    assert run.tierce_charges == 0


def test_forge_tierce_voucher_spends_charges_and_levels_planet() -> None:
    """Regression: prior to 3.1.0 the TierceForge voucher's apply() was a no-op
    and forge_tierce() had no UI caller, leaving the feature unreachable. This
    test pins the backend contract: with 3 charges, calling forge_tierce()
    must consume them and bump the targeted Planet contract level."""
    from belote.belatro.items.registry import register_all_items, registry
    from belote.belatro.items.vouchers import forge_tierce

    register_all_items()
    run = BelAtroRun()
    run.tierce_charges = 3
    run.vouchers.append(TierceForge())

    # Pick the first registered planet so the test is registry-stable.
    planet_id = next(iter(registry.planets.keys()))

    assert forge_tierce(run, planet_id) is True
    assert run.tierce_charges == 0
    # The planet's level-up reward must now be present in contract_levels
    # for the planet's contract_id (e.g. "spades", "tout_atout").
    planet_cls = registry.get_planet(planet_id)
    assert planet_cls is not None
    contract_id = planet_cls().contract_id
    assert contract_id in run.contract_levels
    assert run.contract_levels[contract_id]


def test_le_fou_no_prior_consumable_falls_back_to_random_tarot() -> None:
    """When the player uses LeFou with no previous consumable on record (run
    just started, or the previous one was LeFou itself), the fallback grants
    a random non-LeFou tarot to the consumables tray. Pre-3.1.0 this branch
    was untested; pinning it so the silent-no-op-on-self-copy guard at
    tarots.py:99 (`last_id != self.id`) can't regress."""
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.items.tarots import LeFou

    register_all_items()
    run = BelAtroRun()
    # Defensive guard path: last_consumable_id points to LeFou itself.
    run.last_consumable_id = "le_fou"
    before = len(run.consumables)

    LeFou().use(run, None)

    assert len(run.consumables) == before + 1, "LeFou fallback didn't grant a tarot"
    granted = run.consumables[-1]
    assert not isinstance(granted, LeFou), "LeFou fallback copied itself"


def test_le_jugement_no_op_when_joker_slots_full() -> None:
    """Block-policy regression: LeJugement must NOT silently overflow when the
    player's joker slots are at capacity. The tarot is consumed (its effect is
    one-shot) but no joker is added — the player loses the tarot but doesn't
    have a phantom joker created. Pre-3.1.0 the early-return was implicit; this
    test pins it so a future refactor can't reintroduce silent overflow."""
    from belote.belatro.items.jokers.coinche import CoincheStack
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.items.tarots import LeJugement

    register_all_items()
    run = BelAtroRun()
    run.jokers = [CoincheStack() for _ in range(run.joker_slots)]
    before = list(run.jokers)

    LeJugement().use(run, None)

    assert run.jokers == before, "LeJugement silently grew jokers past slot cap"


def test_la_pretresse_no_op_when_consumable_slots_full() -> None:
    """Block-policy regression: LaPretresse must NOT silently overflow when
    consumable slots are full. Pre-3.1.0 it could partial-grant (1 of 2 planets
    if exactly 1 slot was free); the loop's len-check still blocks any add when
    full, so the no-op behaviour is what we lock here."""
    from belote.belatro.items.registry import register_all_items
    from belote.belatro.items.tarots import LaPretresse, LeChariot

    register_all_items()
    run = BelAtroRun()
    run.consumables = [LeChariot() for _ in range(run.consumable_slots)]
    before = list(run.consumables)

    LaPretresse().use(run, None)

    assert run.consumables == before, "LaPretresse silently grew consumables past slot cap"


def test_forge_tierce_blocked_when_charges_below_three() -> None:
    """Forge must return False (and not consume charges or change levels) when
    the player only has 2 of the required 3 charges."""
    from belote.belatro.items.registry import register_all_items, registry
    from belote.belatro.items.vouchers import forge_tierce

    register_all_items()
    run = BelAtroRun()
    run.tierce_charges = 2
    run.vouchers.append(TierceForge())
    planet_id = next(iter(registry.planets.keys()))

    assert forge_tierce(run, planet_id) is False
    assert run.tierce_charges == 2
    assert not run.contract_levels


# ── Trust tier scaling ─────────────────────────────────────────────────────


def test_trust_tier_buckets() -> None:
    assert TrustTrack(value=0).tier == 0
    assert TrustTrack(value=2).tier == 0
    assert TrustTrack(value=3).tier == 1
    assert TrustTrack(value=5).tier == 2
    assert TrustTrack(value=7).tier == 3
    assert TrustTrack(value=10).tier == 4


def test_trust_mood_strings() -> None:
    assert TrustTrack(value=0).mood() == "degraded"
    assert TrustTrack(value=4).mood() == "sulking"
    assert TrustTrack(value=5).mood() == "neutral"
    assert TrustTrack(value=8).mood() == "eager"
    assert TrustTrack(value=10).mood() == "elated"


def test_partner_joker_tier_scaling_amplifies_effect() -> None:
    """A tier-3 partner joker should score double a tier-1 partner joker."""

    class _PartnerStub(Joker):
        id = "stub"
        name = "Stub"
        description = ""
        is_partner_joker = True

        def on_trick_won(
            self, event: TrickWonEvent, state: dict[str, Any]
        ) -> JokerResult | None:
            return JokerResult(add_chips=10)

    base = ScoreAccumulator(partner_tier=1)
    base.attach_jokers([_PartnerStub()])
    boosted = ScoreAccumulator(partner_tier=3)
    boosted.attach_jokers([_PartnerStub()])

    state = GameState(hands=((), (), (), ()))
    evt = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=(),
        trick_number=1,
        is_last=False,
        card_points=0,
        trump=Suit.HEARTS,
    )
    base_state = base.update_state(state, evt)
    boost_state = boosted.update_state(state, evt)
    # Tier 1 → 1 apply (10 chips). Tier 3 → 2 applies (20 chips).
    assert base_state._chips == 10
    assert boost_state._chips == 20


# ── Betrayal boss ──────────────────────────────────────────────────────────


def test_betrayal_arc_registered() -> None:
    assert BetrayalArc in ALL_BOSS_MODIFIERS


# ── New decks ──────────────────────────────────────────────────────────────


def test_marseille_and_coinche_decks_exist() -> None:
    deck_ids = {d.id for d in STARTING_DECKS}
    assert "marseille" in deck_ids
    assert "coinche" in deck_ids


def test_marseille_deck_sets_announce_flags() -> None:
    run = BelAtroRun(deck_id="marseille")
    assert run.card_enhancements.get("announce_x2") is True
    assert run.card_enhancements.get("no_belote_rebelote") is True


def test_coinche_deck_grants_starting_chips_and_coinche_flag() -> None:
    run = BelAtroRun(deck_id="coinche")
    assert run.permanent_chips == 50
    assert run.card_enhancements.get("start_coinched") is True


# ── New tarots ─────────────────────────────────────────────────────────────


def test_la_maison_dieu_sets_disable_boss_flag() -> None:
    run = BelAtroRun()
    LaMaisonDieu().use(run, context=None)
    assert run.card_enhancements.get("disable_next_boss") is True


def test_le_diable_sets_partner_overcut_flag() -> None:
    run = BelAtroRun()
    LeDiable().use(run, context=None)
    assert run.card_enhancements.get("partner_overcut_round") is True


# ── Registry registration of new content ───────────────────────────────────


def test_phase2_jokers_are_registered() -> None:
    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()
    assert "coinche_stack" in registry.jokers
    assert "tout_streak" in registry.jokers
    assert "tierce_charger" in registry.jokers
    assert "rebelote_echo" in registry.jokers
    assert "quinte_royale" in registry.jokers


def test_phase2_vouchers_and_tarots_are_registered() -> None:
    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()
    assert "capot_insurance" in registry.vouchers
    assert "tierce_forge" in registry.vouchers
    assert "la_maison_dieu" in registry.tarots
    assert "le_diable" in registry.tarots


# ── 3.8.1: belote-pair joker double-fire fix ───────────────────────────────


def test_le_rebelle_fires_once_per_belote_pair() -> None:
    """3.8.1 fix: BeloteAnnouncedEvent fires twice per round (belote, then
    rebelote). LeRebelle's times_mult=3.0 must apply once, not ×9 net."""
    from belote.belatro.items.jokers.contract import LeRebelle

    acc = ScoreAccumulator(target_score=100)
    acc.attach_jokers([LeRebelle()])
    state = GameState(hands=((), (), (), ()), _chips=100, _mult=1.0)

    # First event: belote (is_rebelote=False) — fires.
    e1 = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False)
    state = acc.update_state(state, e1)
    # Second event: rebelote (is_rebelote=True) — gated, must not fire.
    e2 = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True)
    state = acc.update_state(state, e2)

    # ×3 Mult applied exactly once.
    assert state._mult == 3.0
    # Chip subtraction applied exactly once (-20).
    assert state._chips == 80


def test_le_notaire_pays_once_per_belote_pair() -> None:
    """3.8.1 fix: LeNotaire's $5 cash must apply once, not $10 net."""
    from belote.belatro.items.jokers.economy import LeNotaire

    acc = ScoreAccumulator(target_score=100)
    acc.attach_jokers([LeNotaire()])
    state = GameState(hands=((), (), (), ()), _chips=100, _mult=1.0)

    state = acc.update_state(state, BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False))
    state = acc.update_state(state, BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True))

    assert state._bonus_money == 5
    assert state._chips == 80


def test_lagent_double_purchase_flags_run() -> None:
    """3.8.1 fix: LAgentDouble.on_purchase must flag the run so round_driver
    populates the sabotage tricks. Pre-3.8.1 the joker only awarded +4 Mult
    and never triggered the partner-sabotage half of its description."""
    from belote.belatro.items.jokers.corrupted import LAgentDouble

    run = BelAtroRun()
    assert run.agent_double_joker is False
    LAgentDouble().on_purchase(run)
    assert run.agent_double_joker is True
