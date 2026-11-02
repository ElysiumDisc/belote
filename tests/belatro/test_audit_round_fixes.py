"""Regression tests for a batch of BelAtro audit fixes.

Covers: L'Architecte buy-contract legality, all-pass redeal inside
drive_round, capot attribution (unlocks / Pluto / Mercury), joker sabotage vs
boss precedence, L'Avocat effective target, run seeding + ghost filenames,
corrupt-profile loading, FitAbortedError handling, endless-victory summary,
and the shop never offering an owned joker.
"""

from __future__ import annotations

import contextlib
import json
import random
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.core.state import BelatroState, as_belatro
from belote.belatro.engine.event_bus import EventBus, RoundEndEvent
from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
from belote.belatro.partner.partner_state import PartnerState
from belote.deck import Suit
from belote.game import SANS_ATOUT_BID, GameState, Phase, Seat, legal_cards, new_game, start_round

# ── helpers ────────────────────────────────────────────────────────────────


class _BaseUI(RoundUICallbacks):
    def prompt_bid(self, state: GameState) -> Any:
        return None

    def prompt_card(self, state: GameState) -> Any:
        return legal_cards(state, Seat.SOUTH)[0], state

    def on_card_played(self, state: GameState, seat: Seat, card: Any) -> None:
        pass

    def on_trick_end(self, state: GameState, winner: Seat, points: int) -> None:
        pass

    def on_round_end(self, breakdown: object) -> None:
        pass


def _round_state(bidding_round: int = 1) -> GameState:
    state = start_round(new_game(), random.Random(3))
    return replace(state, bidding_round=bidding_round)


# ── 1. L'Architecte buy-contract ───────────────────────────────────────────


def _architecte_ui(
    monkeypatch: pytest.MonkeyPatch, pick: object, seen: list[object]
) -> tuple[Any, BelAtroRun]:
    from belote.belatro.main import UICallbacks
    from belote.belatro.ui.announce import BelAtroAnnounce

    def _picker(reader: object, allowed: object = None) -> object:
        seen.append(allowed)
        return pick

    monkeypatch.setattr(BelAtroAnnounce, "yes_no", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(BelAtroAnnounce, "buy_contract_picker", staticmethod(_picker))
    monkeypatch.setattr(BelAtroAnnounce, "banner", staticmethod(lambda *a, **k: None))
    # Normal bid UI fallback: pass.
    monkeypatch.setattr("belote.ui.prompts.prompt_bid", lambda state, reader: None)
    run = BelAtroRun(deck_id="architecte", seed=1)
    run.card_enhancements["buy_contract"] = True
    run.economy.money = 50
    ui = UICallbacks(
        MagicMock(),
        run,
        MagicMock(),
        MagicMock(),
        ScoreAccumulator(),
        MagicMock(),
        MagicMock(),
        False,
    )
    return ui, run


def test_architecte_round1_offers_only_up_card_suit(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _round_state(1)
    assert state.up_card is not None
    seen: list[object] = []
    ui, run = _architecte_ui(monkeypatch, state.up_card.suit, seen)
    assert ui.prompt_bid(state) == state.up_card.suit
    assert seen == [[state.up_card.suit]]
    assert run.economy.money == 40


def test_architecte_illegal_pick_is_not_charged(monkeypatch: pytest.MonkeyPatch) -> None:
    """TA in round 1 used to cost $10 then crash in place_bid."""
    state = _round_state(1)
    ui, run = _architecte_ui(monkeypatch, Suit.TOUT_ATOUT, [])
    assert ui.prompt_bid(state) is None  # fell through to the normal (pass) UI
    assert run.economy.money == 50


def test_architecte_round2_offers_other_suits_and_specials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _round_state(2)
    assert state.up_card is not None
    seen: list[object] = []
    ui, run = _architecte_ui(monkeypatch, SANS_ATOUT_BID, seen)
    assert ui.prompt_bid(state) == SANS_ATOUT_BID
    allowed = seen[0]
    assert isinstance(allowed, list)
    assert state.up_card.suit not in allowed
    assert Suit.TOUT_ATOUT in allowed and SANS_ATOUT_BID in allowed
    assert len(allowed) == 5
    assert run.economy.money == 40


def test_architecte_round1_drive_round_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end version of the audit repro (picker forced to TA)."""
    from belote.game import legal_cards as _legal

    ui, run = _architecte_ui(monkeypatch, Suit.TOUT_ATOUT, [])
    monkeypatch.setattr(type(ui), "prompt_card", lambda self, s: (_legal(s, Seat.SOUTH)[0], s))
    for name in ("on_card_played", "on_trick_end"):
        monkeypatch.setattr(type(ui), name, lambda self, *a: None)
    monkeypatch.setattr(type(ui), "on_redeal", lambda self, s: None)
    monkeypatch.setattr(type(ui), "prompt_heist", lambda self, s: False)
    acc = ScoreAccumulator()
    drive_round(
        EventBus(), run.partner, ui, acc=acc, seed=0, card_enhancements=dict(run.card_enhancements)
    )
    assert run.economy.money == 50


# ── 2. All-pass redeal ─────────────────────────────────────────────────────


class _PassFirstDealUI(_BaseUI):
    """South passes through the whole first deal, then takes on the redeal."""

    def __init__(self) -> None:
        self.bid_calls = 0
        self.redeals: list[GameState] = []

    def prompt_bid(self, state: GameState) -> Any:
        self.bid_calls += 1
        if self.redeals and state.bidding_round == 1:
            assert state.up_card is not None
            return state.up_card.suit
        return None

    def on_redeal(self, state: GameState) -> None:
        self.redeals.append(state)


def test_all_pass_redeals_and_plays_the_new_deal() -> None:
    from belote.belatro.run.boss import LeRoiMort

    partner = PartnerState()
    ui = _PassFirstDealUI()
    bus = EventBus()
    events: list[object] = []
    bus.subscribe(events.append)
    acc = ScoreAccumulator()
    starts: list[int] = []
    real_start = ScoreAccumulator.trigger_round_start

    def _spy(self: ScoreAccumulator, state: GameState) -> GameState:
        starts.append(1)
        return real_start(self, state)

    with (
        patch("belote.ai.AIPlayer.decide_bid", return_value=None),
        patch.object(ScoreAccumulator, "trigger_round_start", _spy),
        patch.object(type(partner.personality), "should_bid", return_value=False),
    ):
        state = drive_round(
            bus,
            partner,
            ui,
            acc=acc,
            boss=LeRoiMort(),
            seed=5,
            card_enhancements={"traitre_active": True},
        )

    assert len(ui.redeals) == 1
    assert ui.redeals[0].phase == Phase.BIDDING
    assert len(state.completed_tricks) == 8
    assert state.taker == Seat.SOUTH
    # Boss flags survive start_round's reset; round setup ran exactly once.
    assert state.variants.kings_zero is True
    assert state.variants.agent_double_active is True
    assert len(state.variants.sabotage_tricks) == 1
    assert starts == [1]
    # Only the played deal produces a RoundEndEvent.
    assert sum(isinstance(e, RoundEndEvent) for e in events) == 1


def test_all_pass_never_ends_round_in_natural_play() -> None:
    """Audit repro: ~15% of rounds used to end at Phase.DEAL with 0 tricks."""
    from belote.belatro.partner.personality import LeSacrifie

    for seed in range(60):
        state = drive_round(
            EventBus(),
            PartnerState(personality=LeSacrifie()),
            _BaseUI(),
            acc=ScoreAccumulator(),
            seed=seed,
        )
        assert state.phase != Phase.DEAL, seed
        assert len(state.completed_tricks) == 8


# ── 3. Capot attribution + planet rewards ──────────────────────────────────


def _bd(taker_team: int, is_failed: bool = False) -> SimpleNamespace:
    return SimpleNamespace(taker_team=taker_team, is_capot=True, is_failed=is_failed)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (RoundEndEvent(_bd(1), Seat.EAST, Suit.HEARTS, capot=True), False),  # EW capots NS
        (RoundEndEvent(_bd(0), Seat.SOUTH, Suit.HEARTS, capot=True), True),
        (RoundEndEvent(_bd(1, True), Seat.EAST, Suit.HEARTS, capot=True), True),  # NS defenders
        (RoundEndEvent(_bd(0, True), Seat.SOUTH, Suit.HEARTS, capot=True), False),
        (RoundEndEvent(_bd(0), Seat.SOUTH, Suit.HEARTS, capot=True, capot_team=1), False),
        (RoundEndEvent(_bd(1), Seat.EAST, Suit.HEARTS, capot=True, capot_team=0), True),
        (RoundEndEvent(_bd(0), Seat.SOUTH, Suit.HEARTS, capot=False), False),
    ],
)
def test_ns_capot_attribution(event: RoundEndEvent, expected: bool) -> None:
    assert event.ns_capot is expected


def test_ew_capot_does_not_unlock_or_count() -> None:
    from belote.belatro.progression.save import Profile
    from belote.belatro.progression.unlocks import UnlockTracker

    profile = Profile()
    tracker = UnlockTracker(profile, MagicMock())
    tracker.on_event(RoundEndEvent(_bd(1), Seat.EAST, Suit.HEARTS, capot=True, capot_team=1))
    assert profile.stats["total_capots"] == 0
    assert not profile.is_unlocked("l_executeur")
    tracker.on_event(RoundEndEvent(_bd(0), Seat.SOUTH, Suit.HEARTS, capot=True, capot_team=0))
    assert profile.stats["total_capots"] == 1
    assert profile.is_unlocked("l_executeur")


@pytest.mark.parametrize(
    ("taker", "capot_team", "paid"),
    [
        (Seat.SOUTH, 0, True),
        (Seat.EAST, 1, False),
    ],
)
def test_pluto_and_mercury_only_pay_ns(taker: Seat, capot_team: int, paid: bool) -> None:
    acc = ScoreAccumulator()
    acc.contract_levels = {  # type: ignore[assignment]
        "capot": {"capot_bonus": 48},
        "diamonds": {"add_chips": 6, "add_money": 1},
    }
    bd = SimpleNamespace(is_failed=False, taker_total=0, taker_team=capot_team)
    state = BelatroState(hands=((), (), (), ()))
    acc.update_state(
        state,
        RoundEndEvent(
            bd,
            taker,
            Suit.DIAMONDS,
            capot=True,  # type: ignore[arg-type]
            capot_team=capot_team,
        ),
    )
    logged = " ".join(acc._log)
    assert ("Pluton" in logged) is paid
    assert ("Planet (diamonds)" in logged) is paid


def test_pluto_skips_defensive_ns_capot() -> None:
    """EW took the contract, NS defenders took all 8 tricks: Pluto levels up
    the player's own contracts, so it must not pay here."""
    acc = ScoreAccumulator()
    acc.contract_levels = {"capot": {"capot_bonus": 48}}  # type: ignore[assignment]
    bd = SimpleNamespace(is_failed=True, taker_total=0, taker_team=1)
    acc.update_state(
        BelatroState(hands=((), (), (), ())),
        RoundEndEvent(bd, Seat.EAST, Suit.DIAMONDS, capot=True, capot_team=0),  # type: ignore[arg-type]
    )
    assert "Pluton" not in " ".join(acc._log)


def test_drive_round_carries_capot_team() -> None:
    bus = EventBus()
    events: list[object] = []
    bus.subscribe(events.append)
    with patch("belote.belatro.engine.round_driver.is_capot", return_value=1):
        drive_round(bus, PartnerState(), _BaseUI(), acc=ScoreAccumulator(), seed=3)
    end = [e for e in events if isinstance(e, RoundEndEvent)]
    assert len(end) == 1
    assert end[0].capot is True and end[0].capot_team == 1 and end[0].ns_capot is False


# ── 4. Joker sabotage vs boss precedence ───────────────────────────────────


class _AbortError(Exception):
    pass


class _CaptureUI(_BaseUI):
    captured: GameState | None = None

    def prompt_bid(self, state: GameState) -> Any:
        self.captured = state
        raise _AbortError

    def prompt_card(self, state: GameState) -> Any:
        self.captured = state
        raise _AbortError


def _sabotage_tricks(boss: Any, flags: dict[str, object]) -> frozenset[int]:
    ui = _CaptureUI()
    with contextlib.suppress(_AbortError):
        drive_round(
            EventBus(),
            PartnerState(),
            ui,
            acc=ScoreAccumulator(),
            boss=boss,
            seed=1,
            card_enhancements=dict(flags),
        )
    assert ui.captured is not None
    tricks = ui.captured.variants.sabotage_tricks
    assert isinstance(tricks, frozenset)
    return tricks


@pytest.mark.parametrize("flag", ["traitre_active", "agent_double_joker_active"])
def test_boss_sabotage_set_wins_over_joker(flag: str) -> None:
    from belote.belatro.run.boss import BetrayalArc, LAgentDoubleBoss

    assert len(_sabotage_tricks(LAgentDoubleBoss(), {flag: True})) == 3
    assert _sabotage_tricks(BetrayalArc(), {flag: True}) == frozenset(range(4, 9))


def test_joker_sabotage_without_boss_unchanged() -> None:
    assert len(_sabotage_tricks(None, {"traitre_active": True})) == 1
    assert len(_sabotage_tricks(None, {"agent_double_joker_active": True})) == 2


# ── 5/6. _play_blind: L'Avocat effective target + per-round seed ───────────


def _play_blind_harness(
    monkeypatch: pytest.MonkeyPatch, *, total_over: int, seed: int = 11
) -> tuple[Any, BelAtroRun, dict[str, Any]]:
    import belote.belatro.main as bmain
    from belote.belatro.run import boss as boss_mod
    from belote.belatro.ui.announce import BelAtroAnnounce

    game = bmain.BelAtroGame()
    game.reader = MagicMock()
    run = BelAtroRun(seed=seed)
    run.blind_index = 2  # boss blind
    game.run = run
    base_target = run.target_score
    captured: dict[str, Any] = {"base_target": base_target, "margins": []}

    monkeypatch.setattr(boss_mod, "ALL_BOSS_MODIFIERS", [boss_mod.LAvocat])
    for name in ("banner", "boss_reveal"):
        monkeypatch.setattr(BelAtroAnnounce, name, staticmethod(lambda *a, **k: None))
    monkeypatch.setattr("belote.belatro.ui.hud.BelAtroHUD", MagicMock())
    monkeypatch.setattr("belote.belatro.ui.trust_bar.TrustBar", MagicMock())

    final_state = as_belatro(new_game())

    def _fake_drive(**kwargs: Any) -> GameState:
        captured["drive_kwargs"] = kwargs
        return final_state

    monkeypatch.setattr(bmain, "drive_round", _fake_drive)
    monkeypatch.setattr(ScoreAccumulator, "get_total", lambda self, s: 2 * base_target + total_over)
    bd = SimpleNamespace(is_failed=False, is_capot=False, taker_team=0, tricks_ns=8, tricks_ew=0)
    monkeypatch.setattr("belote.scoring.score_round", lambda s: bd)

    real_pre = run.economy.process_round_end

    def _spy_pre(margin: int) -> int:
        captured["margins"].append(margin)
        return real_pre(margin)

    monkeypatch.setattr(run.economy, "process_round_end", _spy_pre)
    return game, run, captured


def test_lavocat_uses_doubled_target_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    game, run, cap = _play_blind_harness(monkeypatch, total_over=100)
    game._play_blind()
    assert not run.run_over
    assert cap["margins"] == [100]  # margin over the 2x target, not the base
    entry = run.history[-1]
    assert entry.target == 2 * cap["base_target"]
    assert entry.status == "WON"


def test_lavocat_big_margin_measured_against_doubled_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 2T + 10 clears 1.5 x base but not 1.5 x the doubled target.
    game, run, _ = _play_blind_harness(monkeypatch, total_over=10)
    run.partner.trust.big_margin_win = MagicMock()  # type: ignore[method-assign]
    run.partner.trust.blind_beaten = MagicMock()  # type: ignore[method-assign]
    game._play_blind()
    run.partner.trust.big_margin_win.assert_not_called()
    run.partner.trust.blind_beaten.assert_called_once()


def test_play_blind_passes_seed_from_run_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    game, _, cap = _play_blind_harness(monkeypatch, total_over=0, seed=77)
    game._play_blind()
    seed1 = cap["drive_kwargs"]["seed"]
    game2, _, cap2 = _play_blind_harness(monkeypatch, total_over=0, seed=77)
    game2._play_blind()
    assert isinstance(seed1, int)
    assert seed1 == cap2["drive_kwargs"]["seed"]


def test_run_gets_a_seed_when_none_given() -> None:
    assert isinstance(BelAtroRun().seed, int)
    assert BelAtroRun(seed=5).seed == 5


def test_ghost_files_do_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.ghost_run import GhostRecorder

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    p1 = GhostRecorder(seed=1, deck_id="classique").save("ante3")
    p2 = GhostRecorder(seed=1, deck_id="classique").save("ante3")
    assert p1 != p2
    assert p1.exists() and p2.exists()


# ── 7. Corrupt / foreign profile loading ───────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"null",
        b'{"stats": null}',
        b'{"unlocked_ids": "abc"}',
        b"\xff\xfe\x00garbage",
        b'{"schema_version": "x"}',
        b"",
        b"{",
        b'{"stats": {"runs_won": "lots"}}',
        b'{"discovered_items": [1, 2]}',
    ],
)
def test_corrupt_profile_falls_back_and_is_backed_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from belote.belatro.progression.save import Profile, SaveManager

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager()
    sm._save_path.write_bytes(payload)
    profile = sm.load_profile()
    assert profile == Profile()
    bak = sm._save_path.with_name("profile.json.bak")
    assert bak.read_bytes() == payload
    assert not sm._save_path.exists()


def test_newer_schema_profile_is_left_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.belatro.progression.save import Profile, SaveManager

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager()
    raw = json.dumps({"schema_version": sm.SCHEMA_VERSION + 1, "unlocked_ids": ["x"]})
    sm._save_path.write_text(raw)
    profile = sm.load_profile()  # must not raise
    assert profile == Profile()
    profile.unlock("le_fanatique")
    sm.save_profile(profile)  # must not clobber the newer file
    assert sm._save_path.read_text() == raw


def test_valid_profile_still_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.progression.save import Profile, SaveManager

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sm = SaveManager()
    p = Profile()
    p.unlock("le_fanatique")
    p.stats["runs_won"] = 3
    sm.save_profile(p)
    assert sm.load_profile() == p


# ── 8/9. BelAtroGame.start: FitAbortedError + endless victory ──────────────


def _start_game(monkeypatch: pytest.MonkeyPatch, menu_run: Any) -> tuple[Any, list[bool]]:
    import belote.belatro.main as bmain
    import belote.belatro.run_summary as rs

    wons: list[bool] = []
    monkeypatch.setattr(rs, "append_summary", lambda run, *, won: wons.append(won))

    class _Menu:
        def __init__(self, *a: object) -> None:
            pass

        def run(self) -> Any:
            return menu_run() if callable(menu_run) else menu_run

    monkeypatch.setattr(bmain, "BelAtroMainMenu", _Menu)
    game = bmain.BelAtroGame()
    return game, wons


def test_fit_aborted_in_menu_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.ui.fit_guard import FitAbortedError

    def _raise() -> None:
        raise FitAbortedError

    game, _ = _start_game(monkeypatch, _raise)
    game.start(MagicMock())  # must not raise


def test_fit_aborted_in_run_loop_ends_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.ui.fit_guard import FitAbortedError

    run = BelAtroRun(seed=1)
    game, wons = _start_game(monkeypatch, run)
    monkeypatch.setattr(game, "_play_blind", MagicMock(side_effect=FitAbortedError))
    game.start(MagicMock())
    assert run.run_over is True
    assert wons == [False]


def test_endless_run_is_summarised_as_won(monkeypatch: pytest.MonkeyPatch) -> None:
    run = BelAtroRun(seed=1)
    run.run_won = True
    run.enter_endless()
    run.run_over = True
    game, wons = _start_game(monkeypatch, run)
    monkeypatch.setattr(game, "_run_loop", lambda: None)
    recorder = MagicMock()
    game._ghost_enabled = False
    game._ghost_recorder = recorder
    game.start(MagicMock())
    assert wons == [True]
    recorder.save.assert_called_once_with(label="won")


# ── B. Shop never offers an owned joker ────────────────────────────────────


def test_shop_excludes_owned_jokers() -> None:
    from belote.belatro.items.registry import registry
    from belote.belatro.run.shop import Shop

    run = BelAtroRun(seed=1)
    owned = {"le_relais", "laccumulateur", "le_premier_sang"}
    run.jokers = [registry.jokers[i]() for i in owned if i in registry.jokers]
    assert run.jokers
    shop = Shop(run)
    for _ in range(200):
        # 5.0.0: owned jokers only come back as deliberate copy offers.
        shop.copy_chance = 0.0
        shop.generate_inventory()
        assert not any(getattr(it, "id", None) in owned for it in shop.inventory)


def test_shop_with_every_joker_owned_offers_no_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from belote.belatro.items.registry import registry
    from belote.belatro.progression.save import Profile
    from belote.belatro.run.shop import Shop

    run = BelAtroRun(seed=2)
    available = registry.get_available_jokers(Profile())
    run.jokers = [cls() for cls in available.values()]
    shop = Shop(run)
    shop.copy_chance = 0.0  # 5.0.0: no copy offers → no owned joker at all
    shop.generate_inventory()
    owned = {j.id for j in run.jokers}
    assert not any(getattr(it, "id", None) in owned for it in shop.inventory)
    assert shop.inventory  # tarot/planet/voucher still offered


# ── Sans Atout from the normal BelAtro bid prompt ──────────────────────────


@pytest.mark.parametrize("pick", [SANS_ATOUT_BID, Suit.TOUT_ATOUT, Suit.SPADES])
def test_belatro_prompt_bid_keeps_special_contracts(
    monkeypatch: pytest.MonkeyPatch, pick: object
) -> None:
    """SANS_ATOUT_BID is the plain string "sans_atout"; pre-4.10.0 the
    `isinstance(res, str)` sentinel filter turned it into a pass."""
    from belote.belatro.main import UICallbacks

    monkeypatch.setattr("belote.ui.prompts.prompt_bid", lambda state, reader: pick)
    run = BelAtroRun(seed=1)
    ui = UICallbacks(
        MagicMock(),
        run,
        MagicMock(),
        MagicMock(),
        ScoreAccumulator(),
        MagicMock(),
        MagicMock(),
        False,
    )
    assert ui.prompt_bid(_round_state(2)) == pick


def test_belatro_prompt_bid_undo_sentinel_is_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro.main import UICallbacks

    monkeypatch.setattr("belote.ui.prompts.prompt_bid", lambda state, reader: "UNDO")
    ui = UICallbacks(
        MagicMock(),
        BelAtroRun(seed=1),
        MagicMock(),
        MagicMock(),
        ScoreAccumulator(),
        MagicMock(),
        MagicMock(),
        False,
    )
    assert ui.prompt_bid(_round_state(2)) is None
