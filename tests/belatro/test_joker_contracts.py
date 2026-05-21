"""4.6.2 audit matrix — per-joker contract pins.

Each test class targets one joker and pins (a) the happy-path trigger,
(b) at least one non-trigger gate, and (c) any audit-flagged behaviour
worth a regression line. Re-emit guards and round-reset semantics are
covered via parametrized cross-cutting tests at the bottom of the file
to avoid 168 line-equivalent boilerplate.

Test patterns lifted from `tests/belatro/test_partner_jokers.py` and
`tests/belatro/test_phase2_content.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from belote.belatro.engine.event_bus import (
    BeloteAnnouncedEvent,
    BidMadeEvent,
    DeclarationScoredEvent,
    RoundEndEvent,
    TrickWonEvent,
)
from belote.belatro.items.base import Joker
from belote.belatro.items.jokers.annonces import (
    LEclat,
    LeCollectionneur,
    LeMathematicien,
    QuinteRoyale,
    RebeloteEcho,
    TierceCharger,
)
from belote.belatro.items.jokers.coinche import CoincheStack, ToutStreak
from belote.belatro.items.jokers.contract import (
    LeDiplomate,
    LeFanatique,
    LePatriote,
    LePuriste,
    LeRebelle,
    LIdeologue,
    LIllusionniste,
)
from belote.belatro.items.jokers.corrupted import (
    LAgentDouble,
    LeDemon,
    LEgoiste,
    LeTraitre,
)
from belote.belatro.items.jokers.economy import (
    LeBanquier,
    LeNotaire,
    LePasseur,
    LePreteur,
)
from belote.belatro.items.jokers.hand_comp import (
    LAccumulateur,
    LaSentinelle,
    LAvare,
    LeFantome,
)
from belote.belatro.items.jokers.trick_timing import (
    LArcEnCiel,
    LeCavalierNoir,
    LeDernierMot,
    LePremierSang,
    LeSergent,
    LExecuteur,
)
from belote.belatro.items.partner_jokers.passive import (
    LaSymbiose,
    LeMiroir,
    LeRelais,
)
from belote.belatro.items.partner_jokers.risky import (
    LAventurier,
    LeMartyr,
    LeParasite,
)
from belote.belatro.items.partner_jokers.shaper import (
    LaSentinelleP,
    LeCalculateur,
    LeGenereux,
)
from belote.belatro.items.registry import register_all_items
from belote.deck import Card, Rank, Suit
from belote.game import Seat


class _OkBreakdown:
    is_failed = False
    taker_total = 120
    defender_total = 42


class _FailBreakdown:
    is_failed = True
    taker_total = 80
    defender_total = 42


def _trick(
    *,
    winner: Seat = Seat.SOUTH,
    cards: tuple[Card, ...] = (),
    trick_number: int = 2,
    is_last: bool = False,
    card_points: int = 10,
    trump: Suit | None = Suit.HEARTS,
    leader_seat: Seat = Seat.SOUTH,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=cards,
        trick_number=trick_number,
        is_last=is_last,
        card_points=card_points,
        trump=trump,
        leader_seat=leader_seat,
    )


def _round_end(
    *,
    failed: bool = False,
    taker_seat: Seat | None = Seat.SOUTH,
    trump: Suit | None = Suit.HEARTS,
    coinche_level: int = 0,
    capot: bool = False,
    hand_remainder: tuple[Card, ...] = (),
) -> RoundEndEvent:
    return RoundEndEvent(
        breakdown=_FailBreakdown() if failed else _OkBreakdown(),
        taker_seat=taker_seat,
        trump=trump,
        capot=capot,
        hand_remainder=hand_remainder,
        coinche_level=coinche_level,
    )


# ── coinche.py ────────────────────────────────────────────────────────────


def test_coinche_stack_pays_per_coinche_level() -> None:
    r = CoincheStack().on_round_end(_round_end(coinche_level=2), {})
    assert r is not None and r.add_mult == 8.0


def test_coinche_stack_skips_failed_round() -> None:
    assert CoincheStack().on_round_end(_round_end(coinche_level=2, failed=True), {}) is None


def test_coinche_stack_skips_ew_taker() -> None:
    assert CoincheStack().on_round_end(_round_end(coinche_level=1, taker_seat=Seat.EAST), {}) is None


def test_tout_streak_advances_only_on_tout_win() -> None:
    j = ToutStreak()
    state: dict[str, Any] = {}
    r = j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    assert r is not None and r.times_mult == 1.5
    r2 = j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT), state)
    assert r2 is not None and r2.times_mult == 2.0


def test_tout_streak_resets_on_tout_failure() -> None:
    j = ToutStreak()
    state: dict[str, Any] = {f"{j.id}_streak": 3}
    j.on_round_end(_round_end(trump=Suit.TOUT_ATOUT, failed=True), state)
    assert state[f"{j.id}_streak"] == 0


def test_tout_streak_non_tout_round_preserves_streak() -> None:
    j = ToutStreak()
    state: dict[str, Any] = {f"{j.id}_streak": 4}
    j.on_round_end(_round_end(trump=Suit.HEARTS), state)
    assert state[f"{j.id}_streak"] == 4


# ── hand_comp.py ──────────────────────────────────────────────────────────


def test_lavare_pays_per_seven_or_eight_in_remainder() -> None:
    rem = (Card(Suit.SPADES, Rank.SEVEN), Card(Suit.HEARTS, Rank.EIGHT))
    r = LAvare().on_round_end(_round_end(hand_remainder=rem), {})
    assert r is not None and r.add_chips == 6 and r.add_money == 2


def test_lavare_no_payout_on_empty_remainder() -> None:
    assert LAvare().on_round_end(_round_end(hand_remainder=()), {}) is None


def test_la_sentinelle_round_start_clears_flags() -> None:
    j = LaSentinelle()
    state: dict[str, Any] = {
        f"{j.id}_had_jack": True,
        f"{j.id}_won_with_jack": True,
    }
    j.on_round_start(state)
    assert state[f"{j.id}_had_jack"] is False
    assert state[f"{j.id}_won_with_jack"] is False


def test_la_sentinelle_pays_when_jack_held_but_unused() -> None:
    j = LaSentinelle()
    state = {f"{j.id}_had_jack": True, f"{j.id}_won_with_jack": False}
    r = j.on_round_end(_round_end(), state)
    assert r is not None and r.times_mult == 3.0


def test_le_fantome_pays_per_unplayed_card() -> None:
    rem = (Card(Suit.SPADES, Rank.SEVEN), Card(Suit.HEARTS, Rank.ACE))
    r = LeFantome().on_round_end(_round_end(hand_remainder=rem), {})
    assert r is not None and r.add_mult == 1.0


def test_laccumulateur_credits_team_not_seat() -> None:
    j = LAccumulateur()
    state = {f"{j.id}_stored_chips": 0}
    cards = (Card(Suit.SPADES, Rank.SEVEN), Card(Suit.HEARTS, Rank.EIGHT))
    j.on_trick_won(_trick(winner=Seat.NORTH, cards=cards), state)
    assert state[f"{j.id}_stored_chips"] == 10


def test_laccumulateur_ignores_opponent_tricks() -> None:
    j = LAccumulateur()
    state = {f"{j.id}_stored_chips": 0}
    cards = (Card(Suit.SPADES, Rank.SEVEN),)
    j.on_trick_won(_trick(winner=Seat.EAST, cards=cards), state)
    assert state[f"{j.id}_stored_chips"] == 0


# ── economy.py ────────────────────────────────────────────────────────────


def test_le_banquier_pays_above_target() -> None:
    state = {"target_score": 80}
    r = LeBanquier().on_round_end(_round_end(), state)
    # _OkBreakdown.taker_total=120 → (120-80)//10 = 4
    assert r is not None and r.add_money == 4


def test_le_banquier_silent_on_failure() -> None:
    assert LeBanquier().on_round_end(_round_end(failed=True), {"target_score": 80}) is None


def test_le_banquier_silent_on_ew_taker() -> None:
    assert LeBanquier().on_round_end(_round_end(taker_seat=Seat.WEST), {"target_score": 80}) is None


def test_le_passeur_pays_when_north_passes() -> None:
    ev = BidMadeEvent(seat=Seat.NORTH, trump=None, contract="normal")
    r = LePasseur().on_bid(ev, {})
    assert r is not None and r.add_money == 2


def test_le_passeur_ignores_south_pass() -> None:
    ev = BidMadeEvent(seat=Seat.SOUTH, trump=None, contract="normal")
    assert LePasseur().on_bid(ev, {}) is None


def test_le_notaire_converts_rebelote_to_cash() -> None:
    ev = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True)
    r = LeNotaire().on_belote(ev, {})
    assert r is not None and r.add_chips == -20 and r.add_money == 5


def test_le_notaire_ignores_first_belote() -> None:
    ev = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=False)
    assert LeNotaire().on_belote(ev, {}) is None


def test_le_notaire_seat_keyed_north_no_op() -> None:
    """Audit pin: LeNotaire / LeRebelle / RebeloteEcho all gate seat==SOUTH on
    rebelote. NORTH-held trump K+Q never triggers them. This test pins the
    current behaviour so a future audit doesn't re-flag it without a deliberate
    design change."""
    ev = BeloteAnnouncedEvent(seat=Seat.NORTH, is_rebelote=True)
    assert LeNotaire().on_belote(ev, {}) is None


def test_le_preteur_floor_bailout() -> None:
    r = LePreteur().on_round_start({"current_money": 0})
    assert r is not None and r.add_money == 15


def test_le_preteur_ceiling_skim() -> None:
    r = LePreteur().on_round_start({"current_money": 60})
    assert r is not None and r.add_money == -5 and r.times_mult == 1.2


def test_le_preteur_quiet_mid_band() -> None:
    assert LePreteur().on_round_start({"current_money": 25}) is None


# ── contract.py ───────────────────────────────────────────────────────────


def test_l_ideologue_only_on_sans_atout() -> None:
    cards = (Card(Suit.SPADES, Rank.JACK), Card(Suit.HEARTS, Rank.JACK))
    r = LIdeologue().on_trick_won(_trick(cards=cards, trump=None), {})
    assert r is not None and r.add_chips == 36  # 2 jacks × 18


def test_l_ideologue_silent_when_trump_set() -> None:
    cards = (Card(Suit.SPADES, Rank.JACK),)
    assert LIdeologue().on_trick_won(_trick(cards=cards, trump=Suit.HEARTS), {}) is None


def test_le_fanatique_only_on_tout_atout_contract() -> None:
    j = LeFanatique()
    state = {"contract": "normal", f"{j.id}_wins": 0}
    assert j.on_trick_won(_trick(), state) is None


def test_le_fanatique_pays_after_fifth_win() -> None:
    j = LeFanatique()
    state = {"contract": "tout_atout", f"{j.id}_wins": 4}
    r = j.on_trick_won(_trick(), state)
    assert r is not None and r.times_mult == 1.5


def test_le_diplomate_pays_on_king_queen_pair() -> None:
    cards = (Card(Suit.SPADES, Rank.KING), Card(Suit.SPADES, Rank.QUEEN))
    r = LeDiplomate().on_trick_won(_trick(cards=cards), {})
    assert r is not None and r.times_mult == 2.0


def test_le_diplomate_silent_on_mismatched_suit() -> None:
    cards = (Card(Suit.SPADES, Rank.KING), Card(Suit.HEARTS, Rank.QUEEN))
    assert LeDiplomate().on_trick_won(_trick(cards=cards), {}) is None


def test_le_patriote_uses_raw_card_points() -> None:
    """Audit pin: LePatriote computes its +50% bonus on raw `card_points()`
    not the boss-aware `card_points_with_modifiers()`. Under jacks_zero/aces_zero/
    kings_zero this means the bonus is paid on cards worth 0 elsewhere in the
    round. Pinning the current contract here so a future change is intentional.
    """
    cards = (Card(Suit.HEARTS, Rank.JACK),)  # 20 pts trump → +10 bonus
    r = LePatriote().on_trick_won(_trick(cards=cards, trump=Suit.HEARTS), {})
    assert r is not None and r.add_chips == 10


def test_le_rebelle_swaps_rebelote_for_mult() -> None:
    ev = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True)
    r = LeRebelle().on_belote(ev, {})
    assert r is not None and r.add_chips == -20 and r.times_mult == 3.0


def test_le_puriste_arms_on_sans_atout_win() -> None:
    state: dict[str, Any] = {}
    LePuriste().on_round_end(_round_end(trump=None), state)
    assert state.get("puriste_triggered") is True


def test_le_puriste_skips_failed_sa() -> None:
    state: dict[str, Any] = {}
    LePuriste().on_round_end(_round_end(trump=None, failed=True), state)
    assert "puriste_triggered" not in state


def test_lillusionniste_bonuses_non_trump_jacks() -> None:
    cards = (Card(Suit.SPADES, Rank.JACK), Card(Suit.HEARTS, Rank.JACK))
    r = LIllusionniste().on_trick_won(_trick(cards=cards, trump=Suit.HEARTS), {})
    assert r is not None and r.add_chips == 18  # only the non-trump (Spades) Jack


# ── corrupted.py ──────────────────────────────────────────────────────────


def test_le_traitre_seat_keyed_to_south() -> None:
    assert LeTraitre().on_trick_won(_trick(winner=Seat.SOUTH), {}).add_mult == 2.5
    assert LeTraitre().on_trick_won(_trick(winner=Seat.NORTH), {}) is None


def test_le_demon_team_keyed() -> None:
    assert LeDemon().on_trick_won(_trick(winner=Seat.SOUTH), {}).add_mult == 3.0
    assert LeDemon().on_trick_won(_trick(winner=Seat.NORTH), {}).add_mult == 3.0
    assert LeDemon().on_trick_won(_trick(winner=Seat.EAST), {}) is None


def test_le_egoiste_nullifies_partner_points() -> None:
    r = LEgoiste().on_trick_won(_trick(winner=Seat.NORTH, card_points=15), {})
    assert r is not None and r.add_chips == -15


def test_lagent_double_seat_keyed_to_south() -> None:
    assert LAgentDouble().on_trick_won(_trick(winner=Seat.SOUTH), {}).add_mult == 4.0
    assert LAgentDouble().on_trick_won(_trick(winner=Seat.NORTH), {}) is None


def test_le_demon_on_purchase_is_idempotent() -> None:
    """4.7.3: LeDemon.on_purchase degrades trust by 3; re-applying it (e.g.,
    via a save/load round-trip or replay-resume tool) must NOT compound the
    cost. The guard lives on `run._applied_purchase_ids`, mirroring
    `_applied_voucher_ids` from 3.9.3.
    """
    from belote.belatro.core.run_state import BelAtroRun

    run = BelAtroRun(seed=1)
    starting_trust = run.partner.trust.value
    j = LeDemon()
    j.on_purchase(run)
    after_first = run.partner.trust.value
    assert after_first == max(0, starting_trust - 3)
    # Second call must be a no-op.
    j.on_purchase(run)
    assert run.partner.trust.value == after_first
    # A fresh LeDemon instance with the same id should also short-circuit on
    # the same run (save/load → distinct Python object, same logical joker).
    LeDemon().on_purchase(run)
    assert run.partner.trust.value == after_first


# ── trick_timing.py ────────────────────────────────────────────────────────


def test_le_premier_sang_arms_on_trick_one_then_pays() -> None:
    j = LePremierSang()
    state: dict[str, Any] = {f"{j.id}_active": False}
    j.on_trick_won(_trick(winner=Seat.SOUTH, trick_number=1), state)
    r = j.on_trick_won(_trick(winner=Seat.SOUTH, trick_number=3), state)
    assert r is not None and r.add_mult == 2.0


def test_le_premier_sang_silent_if_trick_one_lost() -> None:
    j = LePremierSang()
    state: dict[str, Any] = {f"{j.id}_active": False}
    j.on_trick_won(_trick(winner=Seat.EAST, trick_number=1), state)
    assert j.on_trick_won(_trick(winner=Seat.SOUTH, trick_number=2), state) is None


def test_le_sergent_resets_on_loss() -> None:
    j = LeSergent()
    state: dict[str, Any] = {f"{j.id}_streak": 5}
    j.on_trick_won(_trick(winner=Seat.EAST), state)
    assert state[f"{j.id}_streak"] == 0


def test_le_dernier_mot_no_dix_de_der_aware() -> None:
    r = LeDernierMot().on_trick_won(_trick(is_last=True), {"no_dix_de_der": True})
    # Under no_dix_de_der, dix_de_der already 0; joker doesn't double-subtract.
    assert r is not None and r.add_chips == 0 and r.times_mult == 2.0


def test_l_executeur_pays_on_last_trick_only() -> None:
    assert LExecuteur().on_trick_won(_trick(is_last=True), {}).add_chips == 40
    assert LExecuteur().on_trick_won(_trick(is_last=False), {}) is None


def test_le_cavalier_noir_heart_lead_spade_win() -> None:
    cards = (
        Card(Suit.HEARTS, Rank.TEN),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.SPADES, Rank.NINE),
        Card(Suit.SPADES, Rank.JACK),
    )
    r = LeCavalierNoir().on_trick_won(
        _trick(cards=cards, leader_seat=Seat.EAST, winner=Seat.NORTH, trump=Suit.SPADES),
        {},
    )
    assert r is not None and r.times_mult == 3.0


def test_l_arc_en_ciel_non_following_winner_pays() -> None:
    cards = (
        Card(Suit.HEARTS, Rank.TEN),
        Card(Suit.SPADES, Rank.SEVEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.HEARTS, Rank.SEVEN),
    )
    r = LArcEnCiel().on_trick_won(
        _trick(cards=cards, leader_seat=Seat.EAST, winner=Seat.NORTH, trump=Suit.SPADES),
        {},
    )
    assert r is not None and r.add_mult == 2.0


# ── annonces.py ───────────────────────────────────────────────────────────


def test_tierce_charger_grants_charge_per_sequence() -> None:
    ev = DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=50)
    state: dict[str, Any] = {}
    r = TierceCharger().on_declaration(ev, state)
    assert r is not None and r.add_chips == 5
    assert state["_pending_tierce_charge"] == 1


def test_tierce_charger_ignores_ew_declaration() -> None:
    ev = DeclarationScoredEvent(seat=Seat.EAST, declaration_type="sequence", points=50)
    assert TierceCharger().on_declaration(ev, {}) is None


def test_rebelote_echo_pays_on_south_rebelote_only() -> None:
    ev = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True)
    assert RebeloteEcho().on_belote(ev, {}).times_mult == 3.0
    assert (
        RebeloteEcho().on_belote(BeloteAnnouncedEvent(seat=Seat.NORTH, is_rebelote=True), {})
        is None
    )


def test_quinte_royale_arms_then_pays_at_round_end() -> None:
    j = QuinteRoyale()
    state: dict[str, Any] = {}
    j.on_declaration(
        DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=100),
        state,
    )
    assert state[f"{j.id}_armed"] is True
    r = j.on_round_end(_round_end(), state)
    assert r is not None and r.times_mult == 4.0
    # Armed flag consumed by pop()
    assert f"{j.id}_armed" not in state


def test_le_collectionneur_pays_per_annonce_card_in_later_trick() -> None:
    annonce_cards = frozenset(
        {(Suit.SPADES.name, Rank.JACK.name), (Suit.SPADES.name, Rank.NINE.name)}
    )
    cards = (
        Card(Suit.SPADES, Rank.JACK),  # SOUTH plays — Annonce card
        Card(Suit.HEARTS, Rank.SEVEN),  # EAST
        Card(Suit.SPADES, Rank.NINE),  # NORTH plays — Annonce card
        Card(Suit.HEARTS, Rank.EIGHT),  # WEST
    )
    state = {"_ns_annonce_cards": annonce_cards}
    r = LeCollectionneur().on_trick_won(
        _trick(cards=cards, trick_number=2, leader_seat=Seat.SOUTH), state
    )
    assert r is not None and r.add_money == 4 and r.add_mult == 10.0


def test_le_collectionneur_silent_on_trick_one() -> None:
    annonce_cards = frozenset({(Suit.SPADES.name, Rank.JACK.name)})
    cards = (Card(Suit.SPADES, Rank.JACK),)
    assert (
        LeCollectionneur().on_trick_won(
            _trick(cards=cards, trick_number=1), {"_ns_annonce_cards": annonce_cards}
        )
        is None
    )


def test_le_mathematicien_pays_on_multiple_of_five() -> None:
    ev = DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="sequence", points=50)
    r = LeMathematicien().on_declaration(ev, {})
    assert r is not None and r.times_mult == 2.0


def test_le_mathematicien_silent_on_zero_points() -> None:
    """Audit pin: under LeMime (declarations_zero) the round_driver emits
    events with points=0. LeMathematicien must not fire on those."""
    ev = DeclarationScoredEvent(seat=Seat.SOUTH, declaration_type="carre", points=0)
    assert LeMathematicien().on_declaration(ev, {}) is None


def test_l_eclat_triples_trick_with_trump_king() -> None:
    cards = (Card(Suit.HEARTS, Rank.KING),)
    r = LEclat().on_trick_won(_trick(cards=cards, card_points=4, trump=Suit.HEARTS), {})
    assert r is not None and r.add_chips == 8  # 2 × event.card_points = triple total


# ── partner_jokers ────────────────────────────────────────────────────────


def test_le_miroir_pays_on_north_win() -> None:
    assert LeMiroir().on_trick_won(_trick(winner=Seat.NORTH), {}).add_chips == 5
    assert LeMiroir().on_trick_won(_trick(winner=Seat.SOUTH), {}) is None


def test_la_symbiose_pays_on_north_declaration() -> None:
    ev = DeclarationScoredEvent(seat=Seat.NORTH, declaration_type="carre", points=100)
    assert LaSymbiose().on_declaration(ev, {}).times_mult == 1.2


def test_le_relais_one_shot_trick_one() -> None:
    j = LeRelais()
    state = {f"{j.id}_triggered": False}
    j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state)
    assert state[f"{j.id}_triggered"] is True
    # Second trick_number=1 (e.g., replay re-emit) must not double-pay.
    assert j.on_trick_won(_trick(winner=Seat.NORTH, trick_number=1), state) is None


def test_laventurier_both_seats_three_wins() -> None:
    j = LAventurier()
    state: dict[str, Any] = {}
    j.on_round_start(state)
    for _ in range(3):
        j.on_trick_won(_trick(winner=Seat.SOUTH), state)
    for i in range(3):
        r = j.on_trick_won(_trick(winner=Seat.NORTH), state)
        # Trigger fires exactly once, on the third NS-win that crosses (3,3).
        if i == 2:
            assert r is not None and r.times_mult == 2.0
        else:
            assert r is None


def test_le_martyr_triggers_only_if_north_zero_wins() -> None:
    j = LeMartyr()
    state = {f"{j.id}_north_wins": 0}
    assert j.on_round_end(_round_end(), state).times_mult == 3.0


def test_le_martyr_silent_if_north_won_any_trick() -> None:
    j = LeMartyr()
    state = {f"{j.id}_north_wins": 1}
    assert j.on_round_end(_round_end(), state) is None


def test_le_parasite_pays_beyond_two_wins() -> None:
    j = LeParasite()
    state = {f"{j.id}_north_wins": 0}
    for i in range(3):
        r = j.on_trick_won(_trick(winner=Seat.NORTH), state)
        if i < 2:
            assert r is None
        else:
            assert r is not None and r.add_money == 1


def test_le_genereux_per_north_trick() -> None:
    assert LeGenereux().on_trick_won(_trick(winner=Seat.NORTH), {}).add_chips == 3


def test_la_sentinelle_p_pays_when_north_never_leads_trump() -> None:
    j = LaSentinelleP()
    state = {f"{j.id}_trump_led": False}
    r = j.on_round_end(_round_end(), state)
    assert r is not None and r.times_mult == 1.5


def test_le_calculateur_per_north_trick() -> None:
    r = LeCalculateur().on_trick_won(_trick(winner=Seat.NORTH), {"le_calculateur_north_wins": 0})
    assert r is not None and r.add_mult == 0.3


# ── Cross-cutting: re-emit guards on state-mutating handlers ──────────────


# 4.1.0 convention: state-mutating on_round_end jokers must short-circuit on
# `re_emit=True` so replay paths can't double-credit cash or arm flags.
@pytest.mark.parametrize(
    "joker",
    [LeBanquier(), CoincheStack(), ToutStreak(), QuinteRoyale()],
)
def test_round_end_jokers_short_circuit_on_re_emit(joker: Joker) -> None:
    state: dict[str, Any] = {f"{joker.id}_armed": True}
    base = _round_end(coinche_level=2, trump=Suit.TOUT_ATOUT)
    # RoundEndEvent is frozen — stamp re_emit via object.__setattr__ per the
    # `tests/belatro/test_phase2_content.py` convention.
    object.__setattr__(base, "re_emit", True)
    assert joker.on_round_end(base, state) is None


def test_rebelote_echo_short_circuits_on_re_emit() -> None:
    ev = BeloteAnnouncedEvent(seat=Seat.SOUTH, is_rebelote=True)
    object.__setattr__(ev, "re_emit", True)
    assert RebeloteEcho().on_belote(ev, {}) is None


def test_le_collectionneur_short_circuits_on_re_emit() -> None:
    annonce_cards = frozenset({(Suit.SPADES.name, Rank.JACK.name)})
    cards = (Card(Suit.SPADES, Rank.JACK),)
    ev = _trick(cards=cards, trick_number=2)
    object.__setattr__(ev, "re_emit", True)
    assert LeCollectionneur().on_trick_won(ev, {"_ns_annonce_cards": annonce_cards}) is None


# ── Cross-cutting: every on_round_start joker resets cleanly ──────────────


@pytest.mark.parametrize(
    "joker",
    [
        LePremierSang(),
        LeSergent(),
        LeFanatique(),
        LaSentinelle(),
        LAccumulateur(),
        LeRelais(),
        LAventurier(),
        LeMartyr(),
        LeParasite(),
        LaSentinelleP(),
        LeCalculateur(),
    ],
)
def test_on_round_start_clears_state(joker: Joker) -> None:
    # Stuff every plausible per-round key with a non-default sentinel; the
    # joker's on_round_start must reset its OWN keys back to the documented
    # default (False / 0 / not-present). Keys it doesn't own may remain.
    state: dict[str, Any] = {
        f"{joker.id}_active": True,
        f"{joker.id}_streak": 99,
        f"{joker.id}_wins": 99,
        f"{joker.id}_had_jack": True,
        f"{joker.id}_won_with_jack": True,
        f"{joker.id}_stored_chips": 99,
        f"{joker.id}_triggered": True,
        f"{joker.id}_south_wins": 99,
        f"{joker.id}_north_wins": 99,
        f"{joker.id}_trump_led": True,
    }
    joker.on_round_start(state)
    # Pick the canonical keys for this joker and check they got reset.
    # We don't assert *all* keys — just that something owned by the joker
    # was demonstrably reset.
    reset_evidence = any(
        state[k] in (False, 0) for k in state if k.startswith(f"{joker.id}_")
    )
    assert reset_evidence, f"{joker.id} on_round_start did not reset any state key"


# ── Workstream C: partner_tier defensive clamp ────────────────────────────


def test_partner_tier_clamp_oob_high() -> None:
    """4.6.2 hardening: scoring.py line 197 now clamps partner_tier to [0,4].
    A tier=5 corrupted save must degrade to tier=4 (the last index value),
    not raise IndexError mid-round."""
    from belote.belatro.core.scoring import ScoreAccumulator

    acc = ScoreAccumulator(partner_tier=99)
    # Stage a synthetic partner-joker trigger; the test passes if no IndexError
    # is raised when accumulator dispatches a TrickWonEvent with a partner
    # joker attached.
    acc._jokers = [LeMiroir()]
    from belote.game import new_game

    state = new_game()
    state = acc.trigger_round_start(state)
    cards = (Card(Suit.HEARTS, Rank.SEVEN),)
    ev = _trick(winner=Seat.NORTH, cards=cards)
    acc.update_state(state, ev)  # must not raise


def test_partner_tier_clamp_oob_negative() -> None:
    """Negative tier (corrupted save) clamps to 0 — no IndexError, no bonus."""
    from belote.belatro.core.scoring import ScoreAccumulator

    acc = ScoreAccumulator(partner_tier=-3)
    acc._jokers = [LeMiroir()]
    from belote.game import new_game

    state = new_game()
    state = acc.trigger_round_start(state)
    ev = _trick(winner=Seat.NORTH, cards=(Card(Suit.HEARTS, Rank.SEVEN),))
    acc.update_state(state, ev)  # must not raise


# ── Audit matrix: every registered joker is reachable ─────────────────────


def test_every_registered_joker_has_an_id_and_name() -> None:
    """Audit matrix invariant: register_all_items() must yield jokers whose
    id and name are non-empty strings. Catches a forgotten class attribute
    on a newly added joker before it ships."""
    register_all_items()
    from belote.belatro.items.registry import registry

    assert len(registry.jokers) >= 42
    for joker_cls in registry.jokers.values():
        inst = joker_cls()
        assert isinstance(inst.id, str) and inst.id
        assert isinstance(inst.name, str) and inst.name
