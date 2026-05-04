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
