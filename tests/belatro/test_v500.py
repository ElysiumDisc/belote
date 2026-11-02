"""5.0.0 — duplicate-safe jokers, Le Serment fusion, L'Atelier card mods,
Médailles, Capot / Grand Chelem contracts, partner story beats, La Gangrène.
Everything pinned through the real accumulator / shop / run objects."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from belote.belatro.core.card_mods import (
    CardMod,
    CardModOffer,
    apply_mod,
    card_from_key,
    card_key,
    mod_rng,
    remove_enhancement,
)
from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.core.state import BelatroState, as_belatro
from belote.belatro.engine.event_bus import RoundEndEvent, TrickWonEvent
from belote.belatro.items.base import (
    Edition,
    Joker,
    JokerResult,
    assign_copy_indices,
    doubled_result,
)
from belote.belatro.items.jokers.atelier import LaVoyante, LeFerronnier, LeSigillaire, LeVitrier
from belote.belatro.items.jokers.corrupted import LeDemon
from belote.belatro.items.jokers.fusions import LeGeneral, LeTambourMajor, Lucifer
from belote.belatro.items.jokers.tempo import LeCapitaine, LeMarechal, LeMetronome, LHorloger
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.progression.save import Profile
from belote.belatro.run import contracts, fusion, medals
from belote.belatro.run.shop import Shop
from belote.deck import Card, Rank, Suit
from belote.game import Seat, new_game

S, E, N, W = Seat.SOUTH, Seat.EAST, Seat.NORTH, Seat.WEST
H, SP, D, C = Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS


@pytest.fixture(autouse=True)
def _items() -> None:
    register_all_items()


def card(text: str) -> Card:
    from belote.belatro.ghost_run import parse_card

    parsed = parse_card(text)
    assert parsed is not None, text
    return parsed


@dataclass
class _Bd:
    is_failed: bool = False
    taker_total: int = 120
    defender_total: int = 42
    taker_team: int = 0


def trick(
    winner: Seat,
    cards: str = "7♣ 8♣ 9♣ 10♣",
    *,
    n: int = 2,
    leader: Seat = S,
    trump: Suit | None = H,
    last: bool = False,
    pts: int = 10,
) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner,
        cards=tuple(card(c) for c in cards.split()),
        trick_number=n,
        is_last=last,
        card_points=pts,
        trump=trump,
        leader_seat=leader,
    )


def round_end(taker: Seat | None = S, *, failed: bool = False) -> RoundEndEvent:
    return RoundEndEvent(breakdown=_Bd(is_failed=failed), taker_seat=taker, trump=H, capot=False)


def play(
    jokers: list[Joker],
    *events: object,
    mods: dict[str, CardMod] | None = None,
    seed: int = 0,
    story: dict[str, float] | None = None,
) -> tuple[ScoreAccumulator, BelatroState]:
    acc = ScoreAccumulator()
    acc.card_mods = dict(mods or {})
    acc.mod_seed = seed
    acc.story_buff = dict(story or {})
    acc.attach_jokers(jokers)
    state = acc.trigger_round_start(BelatroState(hands=((), (), (), ())))
    for event in events:
        acc.process_event(state, event)
    return acc, acc.seal_round(state)


def mods(**by_card: str) -> dict[str, CardMod]:
    """mods(**{"10♥": "verre"}) → card_mods dict."""
    out: dict[str, CardMod] = {}
    for text, mod_id in by_card.items():
        apply_mod(out, card(text), mod_id)
    return out


# ── duplicate-safe joker state ──────────────────────────────────────────────


def test_copies_get_distinct_state_namespaces() -> None:
    a, b, c = LeMetronome(), LeMetronome(), LeMarechal()
    assign_copy_indices([a, b, c])
    assert (a.copy_index, b.copy_index, c.copy_index) == (0, 1, 0)
    assert a.state_key("tempo") == "le_metronome_tempo"  # unchanged first-copy key
    assert b.state_key("tempo") == "le_metronome#2_tempo"
    assign_copy_indices([b])  # selling the first copy keeps the second's namespace
    assert b.copy_index == 1


def test_two_metronomes_both_keep_the_beat() -> None:
    _, one = play([LeMetronome()], trick(S, n=1), trick(N, n=2), trick(S, n=3))
    _, two = play([LeMetronome(), LeMetronome()], trick(S, n=1), trick(N, n=2), trick(S, n=3))
    # Each beat past the first pays per copy: copies stack, never corrupt.
    assert one._mult == pytest.approx(1 + 1 + 2)
    assert two._mult == pytest.approx(1 + 2 * (1 + 2))
    assert two._joker_state["le_metronome_tempo"] == 3
    assert two._joker_state["le_metronome#2_tempo"] == 3


def test_run_scoped_counters_are_harvested_per_copy() -> None:
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=1)
    first, second = LHorloger(), LHorloger()
    run.add_joker(first)
    run.add_joker(second)
    state = as_belatro(new_game())
    state._joker_state.update({"l_horloger_rounds": 3, "l_horloger#2_rounds": 1})
    BelAtroGame._harvest_round_state(run, state)
    assert run.card_enhancements["l_horloger_rounds"] == 3
    assert run.card_enhancements["l_horloger#2_rounds"] == 1


def test_a_second_le_demon_pays_its_own_cost() -> None:
    run = BelAtroRun(seed=1)
    run.partner.trust.value = 9
    run.add_joker(LeDemon())
    run.add_joker(LeDemon())
    assert run.partner.trust.value == 3


def test_le_jugement_grant_fires_the_purchase_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.items.tarots import LeJugement

    run = BelAtroRun(seed=3)
    run.jokers.clear()
    only = {"le_traitre": registry.jokers["le_traitre"]}
    monkeypatch.setattr(registry, "get_available_jokers", lambda _p: only)
    LeJugement().use(run, None)
    assert [j.id for j in run.jokers] == ["le_traitre"]
    assert run.partner_throws_trick  # the curse came with it


def test_shop_copy_offers() -> None:
    run = BelAtroRun(seed=4)
    run.jokers[:] = []
    run.add_joker(LeMarechal())
    shop = Shop(run, Profile())
    shop.copy_chance = 1.0
    shop.generate_inventory()
    jokers = [i for i in shop.inventory if isinstance(i, Joker)]
    assert jokers and all(j.id == "le_marechal" for j in jokers)
    assert shop.copy_chance == Shop.COPY_CHANCE  # one roll only


def test_fusion_results_are_never_stocked() -> None:
    available = registry.get_available_jokers(Profile(unlocked_ids=list(registry.jokers)))
    for joker_id in ("le_general", "le_tambour_major", "lucifer"):
        assert joker_id in registry.jokers and joker_id not in available


# ── Le Serment ──────────────────────────────────────────────────────────────


def test_doubled_result_math() -> None:
    r = doubled_result(JokerResult(add_chips=5, add_mult=1.5, times_mult=1.5, add_money=2))
    assert (r.add_chips, r.add_mult, r.times_mult, r.add_money) == (10, 3.0, 2.0, 4)
    assert doubled_result(JokerResult(times_mult=3.0)).times_mult == 5.0
    assert doubled_result(JokerResult(add_chips=1)).times_mult == 0.0


def test_oath_fuses_three_copies_into_a_sworn_joker() -> None:
    run = BelAtroRun(seed=5, profile=Profile())
    run.jokers[:] = []
    copies = [LeMarechal(), LeMarechal(), LeMarechal()]
    copies[1].edition = Edition.HOLO
    for j in copies:
        run.add_joker(j)
    found = fusion.available_fusions(run)
    assert [f.kind for f in found] == ["oath"]
    sworn = fusion.fuse(run, found[0])
    assert sworn is not None and sworn.sworn and run.jokers == [sworn]
    assert sworn.edition == Edition.HOLO
    assert sworn.cost == 3 * LeMarechal.cost
    assert sworn.display_name.endswith("✦")
    assert run.profile is not None and fusion.OATH_ID in run.profile.discovered_items
    assert fusion.available_fusions(run) == []  # a Juré is never sworn again


def test_sworn_joker_pays_double() -> None:
    plain, sworn = LeMarechal(), LeMarechal()
    sworn.sworn = True
    _, a = play([plain], trick(S, n=1))
    _, b = play([sworn], trick(S, n=1))
    assert a._mult == pytest.approx(1.5)
    assert b._mult == pytest.approx(2.0)


def test_recipe_fusion_makes_le_general() -> None:
    run = BelAtroRun(seed=6, profile=Profile())
    run.jokers[:] = []
    run.add_joker(LeMetronome())
    run.add_joker(LeMarechal())
    run.add_joker(LeCapitaine())
    (recipe,) = [f for f in fusion.available_fusions(run) if f.kind == "recipe"]
    assert "Le Général" in recipe.label
    made = fusion.fuse(run, recipe)
    assert isinstance(made, LeGeneral)
    assert [type(j) for j in run.jokers] == [LeMetronome, LeGeneral]
    assert run.profile is not None
    assert {"recipe_general", "le_general"} <= set(run.profile.discovered_items)


def test_lucifer_keeps_the_curse() -> None:
    run = BelAtroRun(seed=7)
    run.jokers[:] = []
    run.add_joker(registry.jokers["le_traitre"]())
    run.add_joker(LeDemon())
    (recipe,) = fusion.available_fusions(run)
    made = fusion.fuse(run, recipe)
    assert isinstance(made, Lucifer) and made.is_corrupted and run.partner_throws_trick
    _, st = play([Lucifer()], trick(S), trick(N))
    assert st._mult == pytest.approx((1 + 4) * 1.5 + 4)


def test_tambour_major_skips_one_beat() -> None:
    _, st = play([LeTambourMajor()], trick(S, n=1), trick(S, n=2), trick(E, n=3), trick(S, n=4))
    assert st._mult == pytest.approx(1 + 1 + 2 + 3)  # one lost trick only skips a beat


# ── L'Atelier ───────────────────────────────────────────────────────────────


def test_card_keys_round_trip() -> None:
    c = Card(H, Rank.TEN)
    assert card_from_key(card_key(c)) == c
    assert card_from_key("NOPE_X") is None
    table = mods(**{"10♥": "verre"})
    apply_mod(table, c, "rouge")
    assert table[card_key(c)].label() == "Verre + Sceau Rouge"
    remove_enhancement(table, card_key(c))
    assert table[card_key(c)].enhancement is None and table[card_key(c)].seal == "rouge"


def _seed_where(shatters: bool, n: int = 2, text: str = "10♣") -> int:
    key = card_key(card(text))
    return next(s for s in range(500) if (mod_rng(s, n, key).random() < 0.25) is shatters)


def test_verre_doubles_points_or_shatters() -> None:
    table = mods(**{"10♣": "verre"})
    acc, ok = play([], trick(S, trump=H, pts=10), mods=table, seed=_seed_where(False))
    assert ok._chips == 10 + 10 and acc.shattered == []
    acc, broke = play([], trick(S, trump=H, pts=10), mods=table, seed=_seed_where(True))
    assert broke._chips == 0 and acc.shattered == [card_key(card("10♣"))]


def test_mods_only_pay_on_your_capture() -> None:
    _, st = play([LeFerronnier()], trick(E), mods=mods(**{"10♣": "acier"}))
    assert st._chips == 10 and st._mult == 1.0


def test_acier_retriggers_trick_jokers() -> None:
    _, plain = play([LeMarechal()], trick(S, n=1))
    _, steel = play([LeMarechal()], trick(S, n=1), mods=mods(**{"9♣": "acier"}))
    assert plain._mult == pytest.approx(1.5)
    assert steel._mult == pytest.approx(1.5 * 1.5)


def test_chance_is_seeded() -> None:
    table = mods(**{"8♣": "chance"})
    a = play([], trick(S), mods=table, seed=11)[1]
    b = play([], trick(S), mods=table, seed=11)[1]
    assert (a._chips, a._mult, a._bonus_money) == (b._chips, b._mult, b._bonus_money)
    outcomes = {
        (st._chips, st._mult, st._bonus_money)
        for st in (play([], trick(S), mods=table, seed=s)[1] for s in range(60))
    }
    assert len(outcomes) >= 4  # chips / Mult / $ / ×Mult / nothing


def test_rouge_seal_needs_the_winning_card() -> None:
    table = mods(**{"10♣": "rouge"})
    # Leader S plays 7♣ … W plays 10♣ — the 10 is the winner (all clubs, ♥ trump).
    _, won = play([], trick(W, "7♣ 8♣ 9♣ 10♣", leader=S), mods=table)
    assert won._mult == 1.0  # W isn't us
    _, ours = play([], trick(N, "7♣ 8♣ 10♣ 9♣", leader=S), mods=table)
    assert ours._mult == pytest.approx(3.0)
    _, captured_only = play([], trick(N, "10♣ 8♣ A♣ 9♣", leader=S), mods=table)
    assert captured_only._mult == 1.0


def test_bleu_seal_retriggers_round_end_jokers() -> None:
    _, plain = play([LeCapitaine()], trick(S), round_end(S))
    _, blue = play([LeCapitaine()], trick(S), round_end(S), mods=mods(**{"9♣": "bleu"}))
    assert plain._mult == pytest.approx(5.0)
    assert blue._mult == pytest.approx(9.0)


def test_atelier_jokers_ride_the_capture_hook() -> None:
    table = mods(**{"10♣": "verre", "9♣": "acier", "8♣": "chance", "7♣": "or"})
    seed = _seed_where(False)
    _, st = play(
        [LeVitrier(), LeFerronnier(), LaVoyante(), LeSigillaire()], trick(S), mods=table, seed=seed
    )
    assert st._bonus_money >= 1 + 1  # Voyante + Sigillaire at least
    _, shard = play([LeVitrier()], trick(S), mods=mods(**{"10♣": "verre"}), seed=_seed_where(True))
    assert shard._bonus_money == 3


def test_shop_always_offers_an_atelier_upgrade_and_buying_applies_it() -> None:
    run = BelAtroRun(seed=8)
    run.economy.money = 50
    shop = Shop(run, Profile())
    shop.generate_inventory()
    offers = [i for i in shop.inventory if isinstance(i, CardModOffer)]
    assert len(offers) == 1
    offer = offers[0]
    assert shop.buy_item(shop.inventory.index(offer))
    entry = run.card_mods[card_key(offer.card)]
    assert offer.mod_id in (entry.enhancement, entry.seal)


def test_aristocrate_aces_carry_gold_seals() -> None:
    from belote.belatro.main import _gold_sealed_keys

    run = BelAtroRun(seed=1, deck_id="aristocrate")
    assert run.gold_seal_aces
    assert {k for k, m in run.card_mods.items() if m.seal == "or"} == {
        card_key(Card(s, Rank.ACE)) for s in (SP, H, D, C)
    }
    plain = BelAtroRun(seed=1)
    apply_mod(plain.card_mods, Card(H, Rank.SEVEN), "or")
    assert _gold_sealed_keys(plain) == {"SEVEN_HEARTS"}


# ── Médailles ───────────────────────────────────────────────────────────────


def test_skip_offer_never_a_boss_and_stable() -> None:
    run = BelAtroRun(seed=9)
    first = medals.skip_offer(run)
    assert first is not None and first == medals.skip_offer(run)
    run.blind_index = 1  # next is the boss
    assert medals.skip_offer(run) is None
    run.boss_rush = True
    run.blind_index = 0
    assert medals.skip_offer(run) is None


def test_medals_bend_the_next_shop() -> None:
    run = BelAtroRun(seed=10)
    run.add_joker(LeMarechal())
    for medal_id in ("medal_sommelier", "medal_epicier", "medal_mecene", "medal_tailleur"):
        medals.grant(run, medal_id)
    shop = Shop(run, Profile())
    spent = shop.spend_medals()
    assert len(spent) == 4 and run.medals == []
    assert shop.reroll_cost == 0
    shop.generate_inventory()
    jokers = [i for i in shop.inventory if isinstance(i, Joker)]
    assert len(jokers) == 4 and all(j.cost == 0 for j in jokers)
    (offer,) = [i for i in shop.inventory if isinstance(i, CardModOffer)]
    assert offer.cost == 0


def test_la_cagnotte_pays_at_once() -> None:
    run = BelAtroRun(seed=11)
    run.economy.money = 30
    medals.grant(run, "medal_cagnotte")
    assert run.economy.money == 50 and run.medals == []


def test_feat_medals() -> None:
    run = BelAtroRun(seed=12)
    assert medals.feat_medal(run, capot=False, reached_at=None, insured=False) is None
    assert medals.feat_medal(run, capot=False, reached_at=2, insured=False) is None  # not a boss
    assert medals.feat_medal(run, capot=False, reached_at=5, insured=False, boss=True) is None
    assert (
        medals.feat_medal(run, capot=False, reached_at=4, insured=False, boss=True) in medals.MEDALS
    )
    assert medals.feat_medal(run, capot=True, reached_at=None, insured=False) in medals.MEDALS
    run.feat_medal_ante = (run.ante_number, run.endless_ante_offset)
    assert (
        medals.feat_medal(run, capot=True, reached_at=None, insured=False) is None
    )  # one per ante


def test_target_reached_at_is_tracked() -> None:
    acc = ScoreAccumulator()
    acc.target_score = 25
    acc.attach_jokers([])
    state = acc.trigger_round_start(BelatroState(hands=((), (), (), ())))
    for n in range(1, 5):
        acc.process_event(state, trick(S, n=n, pts=10))
    assert acc.target_reached_at == 3


def test_skip_blind_flow(tui: Any) -> None:
    from belote.belatro.main import BelAtroGame

    game = BelAtroGame()
    run = BelAtroRun(seed=13)
    game.run, game.reader = run, tui.reader("space", "space")
    run.blind_index = 1  # sitting on the Big Blind we skip
    game._skip_blind("medal_epicier")
    assert run.history[-1].status == "SKIPPED" and run.blinds_skipped == 1
    assert run.medals == ["medal_epicier"]
    assert run.blind_index == 2


# ── Contrat Capot / Grand Chelem ────────────────────────────────────────────


def test_contract_blinds_are_seeded_big_blinds_from_ante_two() -> None:
    hits = []
    for seed in range(200):
        run = BelAtroRun(seed=seed)
        run.blind_index = 1
        run.ante_number = 1
        assert contracts.contract_blind(run) is None
        run.ante_number = 6
        kind = contracts.contract_blind(run)
        assert kind == contracts.contract_blind(run)
        hits.append(kind)
        run.blind_index = 0
        assert contracts.contract_blind(run) is None
    assert {contracts.CAPOT, contracts.CHELEM, None} == set(hits)


def _all_tricks(winners: list[Seat], monkeypatch: pytest.MonkeyPatch) -> BelatroState:
    import belote.game as game_mod

    monkeypatch.setattr(game_mod, "compute_trick_winners", lambda *a, **k: list(winners))
    return replace(as_belatro(new_game()), completed_tricks=((),) * 8, trump=H)


def test_contract_made(monkeypatch: pytest.MonkeyPatch) -> None:
    capot = _all_tricks([S, N] * 4, monkeypatch)
    assert contracts.contract_made(contracts.CAPOT, capot)
    assert not contracts.contract_made(contracts.CHELEM, capot)  # South only 4
    chelem = _all_tricks([S] * 5 + [N] * 3, monkeypatch)
    assert contracts.contract_made(contracts.CHELEM, chelem)
    missed = _all_tricks([S] * 7 + [E], monkeypatch)
    assert not contracts.contract_made(contracts.CAPOT, missed)


def test_round_driver_declares_only_when_ns_takes() -> None:
    from belote.belatro.engine.round_driver import RoundUICallbacks, _offer_special_contract
    from belote.game import Phase

    class Yes(RoundUICallbacks):
        def prompt_bid(self, state: Any) -> Any: ...
        def prompt_card(self, state: Any) -> Any: ...
        def on_card_played(self, *a: Any) -> None: ...
        def on_trick_end(self, *a: Any) -> None: ...
        def on_round_end(self, *a: Any) -> None: ...

        def prompt_special_contract(self, state: Any, kind: str) -> bool:
            return True

    @dataclass
    class Ctx:
        ui: Any

    for taker, declared in ((S, True), (N, True), (E, False)):
        st = replace(as_belatro(new_game()), phase=Phase.PLAYING, taker=taker)
        st._joker_state[contracts.OFFER_KEY] = contracts.CAPOT
        _offer_special_contract(Ctx(Yes()), st)  # type: ignore[arg-type]
        assert (contracts.DECLARED_KEY in st._joker_state) is declared


def test_broken_contract_ends_the_run_unless_insured(tui: Any) -> None:
    from belote.belatro.main import BelAtroGame

    game = BelAtroGame()
    run = BelAtroRun(seed=14)
    game.run = run
    st = as_belatro(new_game())
    bd: Any = _Bd(is_failed=False)
    run.capot_insurance = True
    assert game._settle_failed_blind(run, tui.reader("space"), st, bd, 999, 10, True, "capot")
    assert not run.run_over and not run.capot_insurance
    assert not game._settle_failed_blind(run, tui.reader("space"), st, bd, 999, 10, True, "capot")
    assert run.run_over and "Contrat Capot broken" in tui.text


def test_made_contract_rewards(tui: Any) -> None:
    from belote.belatro.main import BelAtroGame

    game = BelAtroGame()
    run = BelAtroRun(seed=15)
    game.run = run
    money, slots = run.economy.money, run.joker_slots
    game._reward_contract(run, tui.reader("space"), contracts.CHELEM)
    assert run.economy.money >= money + 25 and run.joker_slots == slots + 1
    assert run.medals_earned == 2  # two Médailles (La Cagnotte would pay at once)
    assert run.capot_contracts_won == 1


# ── partner story beats ─────────────────────────────────────────────────────


def test_story_beats_priority_and_once_per_run() -> None:
    from belote.belatro.partner.story import RoundFacts, grant, next_beat

    run = BelAtroRun(seed=16)
    facts = RoundFacts(trust_before=3, trust_after=6, won=True, ns_capot=True)
    beat = next_beat(run, facts)
    assert beat is not None and beat.id == "les_retrouvailles"
    grant(run, beat)
    assert run.story_buff == {"times_mult": 1.25}
    after = next_beat(run, facts)
    assert after is not None and after.id == "le_premier_capot"
    assert next_beat(run, RoundFacts(trust_before=5, trust_after=5, won=True)) is None


def test_story_buffs_money_trust_and_next_round() -> None:
    from belote.belatro.partner.story import BEATS, grant

    run = BelAtroRun(seed=17)
    run.partner.trust.value = 1
    grant(run, BEATS["au_bord_du_divorce"])
    assert run.partner.trust.value == 3
    money = run.economy.money
    grant(run, BEATS["la_chute"])
    assert run.economy.money == money + 3
    grant(run, BEATS["la_trahison"])
    _, st = play([], story=run.story_buff)
    assert st._chips == 20
    assert "{partner}" not in " ".join(BEATS["la_trahison"].text("Le Flambeur"))


def test_story_buff_is_spent_by_the_next_round() -> None:
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=18)
    run.story_buff.update({"chips": 10, "mult": 2.0})
    acc = BelAtroGame._build_accumulator(run)
    assert acc.story_buff == {"chips": 10, "mult": 2.0} and run.story_buff == {}


def test_story_interstitial_renders(tui: Any) -> None:
    from belote.belatro.partner.story import BEATS
    from belote.belatro.ui.announce import BelAtroAnnounce

    BelAtroAnnounce.story(BEATS["les_jumeaux"], "Le Stratège", tui.reader("space"))
    assert "LES JUMEAUX" in tui.text and "Le Stratège" in tui.text
    assert "×1.5 Mult next round" in tui.text


# ── La Gangrène ─────────────────────────────────────────────────────────────


def test_gangrene_rots_and_spreads() -> None:
    from belote.belatro.run.boss import BOSS_BY_ID, rot_joker

    run = BelAtroRun(seed=19)
    run.jokers[:] = []
    run.add_joker(LeMarechal())
    run.jokers[0].edition = Edition.FOIL
    message = BOSS_BY_ID["la_gangrene"]().on_reveal(run)
    assert run.gangrene_active and message and "Le Maréchal" in message
    assert run.jokers[0].is_corrupted and run.jokers[0].edition == Edition.FOIL
    assert rot_joker(run) is None  # nothing left to rot
    assert run.gangrene_rotted == 1


# ── Le Carnet de Parties ────────────────────────────────────────────────────


def test_carnet_verdicts() -> None:
    from belote.carnet import LastRound, verdict

    chute = LastRound(
        ns_took=True, failed=True, capot=False, ns_capot=False, taker_pts=92, defender_pts=94
    )
    assert verdict(won=False, ns=900, ew=1010, rounds=9, deficit=0, last=chute) == (
        "You chutéed on a 92 vs 94 — brutal."
    )
    capot = LastRound(
        ns_took=True, failed=False, capot=True, ns_capot=True, taker_pts=252, defender_pts=0
    )
    assert "capot" in verdict(won=True, ns=1100, ew=700, rounds=8, deficit=0, last=capot)
    assert "Came back" in verdict(won=True, ns=1001, ew=950, rounds=9, deficit=-320, last=None)
    assert verdict(won=True, ns=1003, ew=987, rounds=9, deficit=0, last=None).startswith("Photo")
    assert verdict(won=False, ns=300, ew=1010, rounds=9, deficit=0, last=None).startswith("Flat")
    assert "Efficient" in verdict(won=True, ns=1010, ew=800, rounds=4, deficit=0, last=None)


def test_carnet_keeps_five_valid_entries(tmp_path: Any) -> None:
    from belote.carnet import carnet_lines, conform_entries
    from belote.stats import Statistics, StatisticsManager

    mgr = StatisticsManager(tmp_path / "stats.json")
    for i in range(7):
        mgr.add_recent_game(
            {
                "date": "2026-11-02",
                "won": i % 2 == 0,
                "ns": i,
                "ew": 0,
                "rounds": 3,
                "difficulty": "medium",
                "verdict": f"game {i}",
            }
        )
    reloaded = StatisticsManager(tmp_path / "stats.json").load_stats()
    assert [e["verdict"] for e in reloaded.recent_games] == [f"game {i}" for i in (6, 5, 4, 3, 2)]
    assert conform_entries([{"won": "yes"}, 3, None]) == []
    assert Statistics.from_dict({"recent_games": "junk"}).recent_games == []
    assert carnet_lines([])[0].strip() == "(no finished games yet)"
    assert "02 Nov  W 6–0  game 6" in carnet_lines(reloaded.recent_games)[0]


def test_carnet_record_uses_the_last_round(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote import carnet

    @dataclass
    class Bd:
        taker_team: int = 0
        table_taker_pts: int = 80
        taker_declarations: int = 0
        taker_belote: int = 20
        table_defender_pts: int = 82
        defender_declarations: int = 20
        defender_belote: int = 0
        is_failed: bool = True
        is_capot: bool = False
        tricks_ns: int = 4

    carnet.note_round(Bd())  # type: ignore[arg-type]
    state = replace(new_game(), team_scores=(700, 1050))
    entry = carnet.record_game(state, won=False, difficulty="hard")
    assert entry["verdict"] == "You chutéed on a 100 vs 102 — brutal."
    assert carnet._last_round is None  # reset for the next game


# ── shop screen ─────────────────────────────────────────────────────────────


def _screen_shop(seed: int, monkeypatch: pytest.MonkeyPatch) -> Shop:
    run = BelAtroRun(seed=seed)
    run.economy.money = 100
    shop = Shop(run)
    inv = [LeCapitaine(), CardModOffer(card=Card(H, Rank.TEN), mod_id="verre", cost=4)]
    monkeypatch.setattr(shop, "generate_inventory", lambda: setattr(shop, "inventory", list(inv)))
    return shop


def test_shop_k_skips_the_next_blind(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _screen_shop(20, monkeypatch)
    medal = shop.skip_offer()
    assert medal is not None
    ShopScreen(shop, tui.reader("k", "y")).run()
    assert shop.skip_next and shop.skip_medal == medal.id
    assert f"K: skip it for {medal.name}" in tui.text
    assert "on 10♥" in tui.text  # the Atelier card


def test_shop_fuse_action(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _screen_shop(21, monkeypatch)
    shop.run.jokers[:] = []
    for _ in range(3):
        shop.run.add_joker(LeMarechal())
    # 2 items → actions start at index 2: Reroll, Fuse.
    ShopScreen(shop, tui.reader("right", "right", "right", "enter", "1", "space", "esc")).run()
    assert [j.sworn for j in shop.run.jokers] == [True]
    assert "LE SERMENT" in tui.text


def test_shop_strip_scrolls_when_cards_overflow(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.ui.shop import ShopScreen

    tui.resize(80, 32)  # the shop's floor (require_minimum)
    shop = _screen_shop(22, monkeypatch)
    many = [LeCapitaine() for _ in range(7)]
    monkeypatch.setattr(shop, "generate_inventory", lambda: setattr(shop, "inventory", many))
    screen = ShopScreen(shop, tui.reader(*["right"] * 6, "esc"))
    screen.run()
    first, count = screen._window(7, 80)
    assert count == 4 and first <= 6 < first + count
    assert screen._card_col(0, 7, 80) == -1  # scrolled out


# ── L'Usurier ───────────────────────────────────────────────────────────────


def _visited_run(seed_from: int = 0) -> BelAtroRun:
    from belote.belatro.run import usurier

    for seed in range(seed_from, seed_from + 200):
        run = BelAtroRun(seed=seed)
        run.ante_number = 2
        if usurier.visits(run):
            return run
    raise AssertionError("no visit in 200 seeds")


def test_usurier_never_visits_ante_one_and_is_seeded() -> None:
    from belote.belatro.run import usurier

    visits = []
    for seed in range(100):
        run = BelAtroRun(seed=seed)
        assert not usurier.visits(run)
        run.ante_number = 3
        assert usurier.visits(run) == usurier.visits(run)
        visits.append(usurier.visits(run))
    assert 25 < sum(visits) < 75


def test_borrow_once_then_repay_in_parts() -> None:
    from belote.belatro.run import usurier

    run = _visited_run()
    run.economy.money = 5
    assert usurier.borrow(run)
    assert (run.economy.money, run.loan_debt, run.loans_taken) == (35, 30, 1)
    assert not usurier.borrow(run)  # one loan at a time
    run.economy.money = 10
    assert usurier.repay(run) == 10 and run.loan_debt == 20 and run.economy.money == 0
    assert usurier.repay(run) == 0
    run.economy.money = 50
    assert usurier.repay(run) == 20 and run.loan_debt == 0 and run.economy.money == 30


def test_debt_compounds_each_ante_and_seizes_at_ninety() -> None:
    from belote.belatro.run import usurier

    run = BelAtroRun(seed=1)
    run.loan_debt = 30
    seen = []
    for _ in range(5):
        usurier.accrue(run)
        seen.append(run.loan_debt)
    assert seen == [36, 44, 53, 64, 77]
    run.economy.money = 4
    run.jokers[:] = []
    run.add_joker(LeCapitaine())  # sells for 2
    run.add_joker(registry.jokers["le_traitre"]())  # corrupted: left alone
    run.add_joker(LeMarechal())  # sells for 3
    lines = usurier.accrue(run)  # 77 → 93
    assert "93" in lines[0] and any("seizes $4" in line for line in lines)
    # 93 - 4 = 89 < 90 after the money: no joker taken
    assert [j.id for j in run.jokers] == ["le_capitaine", "le_traitre", "le_marechal"]
    run.loan_debt, run.economy.money = 120, 0
    usurier.accrue(run)  # 144 → seizes jokers rightmost first, skipping the corrupted
    assert run.loan_debt == 144 - 3 - 2 and [j.id for j in run.jokers] == ["le_traitre"]


def test_no_debt_no_accrual() -> None:
    from belote.belatro.run import usurier

    assert usurier.accrue(BelAtroRun(seed=2)) == []


def test_shop_loan_and_repay_buttons(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.ui.shop import ShopScreen

    shop = _screen_shop(0, monkeypatch)
    run = _visited_run()
    run.economy.money = 0
    shop.run = run
    screen = ShopScreen(shop, tui.reader())
    assert screen._actions() == ["reroll", "loan"]
    # 2 items, Reroll, Loan → LEFT from the first item wraps to Loan.
    ShopScreen(shop, tui.reader("left", "enter", "y", "space", "esc")).run()
    assert run.loan_debt == 30 and run.economy.money == 30
    assert "Debt: $30" in tui.text
    assert ShopScreen(shop, tui.reader())._actions() == ["reroll", "repay"]
    ShopScreen(shop, tui.reader("left", "enter", "space", "esc")).run()
    assert run.loan_debt == 0 and "debt cleared" in tui.text


def test_ante_start_announces_interest(tui: Any) -> None:
    from belote.belatro.main import BelAtroGame

    game = BelAtroGame()
    run = BelAtroRun(seed=3)
    run.loan_debt = 50
    game.run = run
    game._start_ante(run, tui.reader("space"))
    assert run.loan_debt == 60 and "your debt grows $50 → $60" in tui.text
