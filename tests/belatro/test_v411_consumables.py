"""4.11.0 tarots (Le Juge, L'Amoureux), planet (Neptune), voucher (Le
Téléphone) and the 13th starting deck (Le Complice) with its unlock."""

from __future__ import annotations

from typing import Any

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.core.state import BelatroState
from belote.belatro.engine.event_bus import TrickWonEvent
from belote.belatro.items.planets import Neptune
from belote.belatro.items.registry import register_all_items, registry
from belote.belatro.items.tarots import LAmoureux, LeJuge
from belote.belatro.items.vouchers import LeTelephone
from belote.belatro.progression.save import Profile, SaveManager
from belote.belatro.progression.unlocks import UnlockTracker
from belote.belatro.run.boss import peek_upcoming_boss
from belote.belatro.run.decks import (
    COMPLICE_BOSSES_REQUIRED,
    COMPLICE_UNLOCK_ID,
    STARTING_DECKS,
    unlocked_decks,
)
from belote.belatro.run.shop import Shop
from belote.deck import Suit
from belote.game import Seat


def test_new_consumables_registered() -> None:
    register_all_items()
    assert registry.tarots["le_juge"] is LeJuge
    assert registry.tarots["l_amoureux"] is LAmoureux
    assert registry.planets["neptune"] is Neptune
    assert registry.vouchers["le_telephone"] is LeTelephone


# ── Le Juge ────────────────────────────────────────────────────────────────


def test_le_juge_rerolls_the_upcoming_boss_once_per_ante() -> None:
    run = BelAtroRun(seed=11)
    juge = LeJuge()
    run.consumables.append(juge)
    before = peek_upcoming_boss(run)
    assert run.consume(juge) is True
    assert run.upcoming_boss_id is not None and run.upcoming_boss_id != before.id
    assert run.last_tarot_message and before.name in run.last_tarot_message
    # A second Le Juge this ante is refused and stays in the tray.
    second = LeJuge()
    run.consumables.append(second)
    assert run.consume(second) is False
    assert second in run.consumables
    assert "already rerolled" in (run.last_tarot_message or "")
    # Next ante: allowed again.
    run.ante_number += 1
    assert run.consume(second) is True


def test_pick_boss_uses_the_rerolled_boss(tui: Any) -> None:
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=5, profile=Profile())
    run.consume(LeJuge())
    chosen = run.upcoming_boss_id
    run.blind_index = 2
    boss = BelAtroGame._pick_boss(run, tui.reader(default=None))
    assert boss is not None and boss.id == chosen
    assert run.upcoming_boss_id is None  # consumed
    assert run.profile is not None and chosen in run.profile.discovered_items


def test_lazy_boss_roll_draws_like_before() -> None:
    """Without Le Juge, the boss draw is the plain rng.choice of old."""
    import random

    from belote.belatro.run.boss import ALL_BOSS_MODIFIERS, take_upcoming_boss

    run = BelAtroRun(seed=99)
    mirror = random.Random()
    mirror.setstate(run._get_rng().getstate())
    assert take_upcoming_boss(run).id == mirror.choice(ALL_BOSS_MODIFIERS).id


def test_le_juge_refuses_a_pinned_challenge_boss() -> None:
    run = BelAtroRun(seed=1, challenge=True, challenge_boss_id="le_mime")
    assert LeJuge().refusal(run) is not None


# ── L'Amoureux ─────────────────────────────────────────────────────────────


def test_amoureux_raises_trust_or_pays_when_full() -> None:
    run = BelAtroRun(seed=1)
    run.partner.trust.value = 5
    run.consume(LAmoureux())
    assert run.partner.trust.value == 7
    run.partner.trust.value = 10
    money = run.economy.money
    run.consume(LAmoureux())
    assert run.partner.trust.value == 10 and run.economy.money == money + 3


# ── Neptune ────────────────────────────────────────────────────────────────


def _last_trick(winner: Seat) -> TrickWonEvent:
    return TrickWonEvent(
        winner=winner, cards=(), trick_number=8, is_last=True, card_points=0, trump=Suit.CLUBS
    )


@pytest.mark.parametrize(
    ("winner", "flags", "expected"),
    [(Seat.NORTH, {}, 50), (Seat.EAST, {}, 0), (Seat.SOUTH, {"no_dix_de_der": True}, 0)],
)
def test_neptune_levels_dix_de_der(winner: Seat, flags: dict[str, Any], expected: int) -> None:
    run = BelAtroRun(seed=1)
    Neptune().use(run)
    Neptune().use(run)  # two levels stack
    assert run.contract_levels["dix_de_der"] == {"last_trick_chips": 50}
    acc = ScoreAccumulator(contract_levels=run.contract_levels)  # type: ignore[arg-type]
    state = acc.trigger_round_start(BelatroState(hands=((), (), (), ())))
    if flags:
        state._joker_state.update(flags)
    acc.process_event(state, _last_trick(winner))
    assert acc.seal_round(state)._chips == expected


# ── Le Téléphone ───────────────────────────────────────────────────────────


def _telephone_run(seed: int) -> BelAtroRun:
    run = BelAtroRun(seed=seed)
    LeTelephone().apply(run)
    run.economy.money = 100
    return run


def test_telephone_offers_partner_jokers_into_partner_slots() -> None:
    register_all_items()
    offers = 0
    for seed in range(30):
        run = _telephone_run(seed)
        shop = Shop(run, Profile())
        shop.generate_inventory()
        partner_offers = [i for i in shop.inventory if getattr(i, "for_partner", False)]
        assert len(partner_offers) <= 1
        if not partner_offers:
            continue
        offers += 1
        item = partner_offers[0]
        assert item.is_partner_joker
        jokers_before = list(run.jokers)
        assert shop.buy_item(shop.inventory.index(item))
        assert run.partner.jokers == [item] and run.jokers == jokers_before
    assert 5 < offers < 25  # "occasionally" (50% per shop)


def test_telephone_partner_slots_fill_up() -> None:
    from belote.belatro.items.partner_jokers.passive import LeMiroir

    run = _telephone_run(2)
    run.partner.jokers = [LeMiroir(), LeMiroir()]
    item = LeMiroir()
    item.for_partner = True
    shop = Shop(run, Profile())
    shop.inventory = [item]
    assert not shop.buy_item(0) and shop.last_buy_failure == "slots_full"


def test_telephone_only_appends_to_the_normal_shop() -> None:
    """The partner offer is drawn last: the rest of the shop rolls exactly as
    it would without the voucher."""
    register_all_items()
    for seed in range(10):
        plain, phone = BelAtroRun(seed=seed), _telephone_run(seed)
        a, b = Shop(plain, Profile()), Shop(phone, Profile())
        a.generate_inventory()
        b.generate_inventory()
        ids_a = [i.id for i in a.inventory]
        ids_b = [i.id for i in b.inventory if not getattr(i, "for_partner", False)]
        assert ids_a == ids_b


def test_partner_slot_jokers_score() -> None:
    from belote.belatro.items.partner_jokers.passive import LeMiroir
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=1)
    run.partner.jokers.append(LeMiroir())
    acc = BelAtroGame._build_accumulator(run)
    assert any(isinstance(j, LeMiroir) for j in acc._jokers)


# ── Le Complice deck ───────────────────────────────────────────────────────


def test_complice_is_the_13th_deck_and_locked_by_default() -> None:
    assert len(STARTING_DECKS) == 13
    deck = STARTING_DECKS[-1]
    assert deck.id == "complice" and deck.unlock_id == COMPLICE_UNLOCK_ID
    assert deck not in unlocked_decks(Profile())
    assert len(unlocked_decks(Profile())) == 12
    profile = Profile()
    profile.unlock(COMPLICE_UNLOCK_ID)
    assert deck in unlocked_decks(profile)


def test_complice_starting_state() -> None:
    register_all_items()
    run = BelAtroRun(deck_id="complice", seed=4)
    assert run.economy.money == 2
    assert run.partner.trust.value == 7
    assert len(run.partner.jokers) == 1 and run.partner.jokers[0].is_partner_joker
    assert run.jokers == []
    again = BelAtroRun(deck_id="complice", seed=4)
    assert again.partner.jokers[0].id == run.partner.jokers[0].id  # seeded


def test_complice_unlocks_after_enough_boss_wins(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    tracker = UnlockTracker(Profile(), SaveManager())
    for _ in range(COMPLICE_BOSSES_REQUIRED - 1):
        tracker.notify_boss_defeated()
    assert not tracker.profile.is_unlocked(COMPLICE_UNLOCK_ID)
    tracker.notify_boss_defeated()
    assert tracker.profile.is_unlocked(COMPLICE_UNLOCK_ID)
    assert tracker.profile.stats["bosses_defeated"] == COMPLICE_BOSSES_REQUIRED
    assert "Le Complice" in tracker.drain_announcements()[-1]
    # Persisted, and an old save without the counter still loads.
    assert SaveManager().load_profile().stats["bosses_defeated"] == COMPLICE_BOSSES_REQUIRED


def test_old_profile_without_bosses_counter_loads(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    mgr = SaveManager()
    mgr._save_path.write_text(json.dumps({"stats": {"runs_won": 2}, "unlocked_ids": ["x"]}))
    profile = mgr.load_profile()
    assert profile.stats["bosses_defeated"] == 0 and profile.stats["runs_won"] == 2


def test_inventory_lists_partner_slot_jokers(tui: Any) -> None:
    from belote.belatro.items.partner_jokers.passive import LeMiroir
    from belote.belatro.ui.inventory import _build_entries

    run = BelAtroRun(seed=1)
    run.partner.jokers.append(LeMiroir())
    entries = _build_entries(run)
    assert any(e.category == "PARTNER JOKERS" and "Le Miroir" in e.title for e in entries)


def test_first_win_no_longer_announces_decks_that_were_never_locked() -> None:
    """4.11.0: notify_run_won used to 'unlock' Le Républicain / L'Ermite (never
    locked) and announce new decks; it now just counts the win."""
    tracker = UnlockTracker(Profile(), SaveManager())
    tracker.notify_run_won()
    assert tracker.profile.stats["runs_won"] == 1
    assert not any("Starting Decks" in a for a in tracker.pending_announcements)
    assert "le_republicain" not in tracker.profile.unlocked_ids


def test_statistics_screen_shows_boss_blinds_won() -> None:
    from belote.belatro import integration

    mgr = SaveManager()
    profile = mgr.load_profile()
    profile.stats["bosses_defeated"] = 7
    mgr.save_profile(profile)
    assert any("Boss Blinds Won:   7" in line for line in integration.stats_lines())
