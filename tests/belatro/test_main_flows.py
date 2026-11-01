"""`belote.belatro.main`: the UICallbacks wrappers around the classic prompts,
the Blind → Shop → Advance run loop, `_play_blind` phases and the `belatro`
entry point — driven through the harness with real rounds where cheap."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

import pytest

import belote.belatro.main as bmain
from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.core.scoring import ScoreAccumulator
from belote.belatro.core.state import as_belatro
from belote.belatro.items.registry import register_all_items
from belote.belatro.progression.save import Profile, SaveManager
from belote.belatro.ui import announce
from belote.belatro.ui.hud import BelAtroHUD
from belote.belatro.ui.trust_bar import TrustBar
from belote.deck import Card, Rank, Suit
from belote.game import SANS_ATOUT_BID, Phase, Seat, TrickCard, new_game, start_round
from belote.input import Key
from belote.ui import prompts
from tests.harness import TUI, ScriptedReader, raw_char


@pytest.fixture
def run() -> BelAtroRun:
    register_all_items()
    return BelAtroRun(seed=3)


def _cb(
    run: BelAtroRun, reader: ScriptedReader, profile: Profile | None = None
) -> bmain.UICallbacks:
    return bmain.UICallbacks(
        reader,
        run,
        profile or Profile(),
        SaveManager(),
        ScoreAccumulator(),
        BelAtroHUD(run),
        TrustBar(run.partner.trust),
        show_north=False,
    )


def _bid_state(rnd: int = 1) -> Any:
    return as_belatro(
        replace(start_round(new_game(), __import__("random").Random(0)), bidding_round=rnd)
    )


def _play_state() -> Any:
    s = start_round(new_game(), __import__("random").Random(0))
    return as_belatro(
        replace(s, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH, turn=Seat.SOUTH)
    )


@pytest.fixture
def run_keys() -> Any:
    prompts.register_extension_keys(*bmain._RUN_KEYS)
    yield
    prompts.unregister_extension_keys(*bmain._RUN_KEYS)


# ── prompt_bid ──────────────────────────────────────────────────────────────


def test_prompt_bid_take_pass_undo_and_sans_atout(tui: TUI, run: BelAtroRun) -> None:
    state = _bid_state(1)
    assert _cb(run, tui.reader("enter")).prompt_bid(state) == state.up_card.suit
    assert _cb(run, tui.reader("p")).prompt_bid(state) is None
    assert _cb(run, tui.reader("z")).prompt_bid(state) is None  # UNDO → pass
    # Pre-4.10.0 SA (a plain string) was swallowed by the "UI sentinel" filter.
    assert _cb(run, tui.reader("n")).prompt_bid(_bid_state(2)) == SANS_ATOUT_BID


def test_prompt_bid_quit_raises_keyboard_interrupt(tui: TUI, run: BelAtroRun) -> None:
    with pytest.raises(KeyboardInterrupt):
        _cb(run, tui.reader("q")).prompt_bid(_bid_state())


def test_prompt_bid_overlay_toggles_top_hud(tui: TUI, run: BelAtroRun, run_keys: None) -> None:
    state = _bid_state(1)
    assert announce.is_top_hud_visible()
    assert _cb(run, tui.reader("i", "enter")).prompt_bid(state) == state.up_card.suit
    assert not announce.is_top_hud_visible()
    # Inventory key during bidding is an unhandled extension key → pass.
    assert _cb(run, tui.reader("v")).prompt_bid(state) is None


def test_prompt_bid_architecte_buys_contract(tui: TUI, run: BelAtroRun) -> None:
    run.card_enhancements["buy_contract"] = True
    run.economy.money = 25
    state = _bid_state(1)
    r = tui.reader(raw_char("y"), "enter", "space")
    assert _cb(run, r).prompt_bid(state) == state.up_card.suit
    assert run.economy.money == 15
    assert r.exhausted
    text = tui.text
    assert "L'Architecte: buy the contract for $10?" in text
    assert "Pick a contract ($10)" in text
    assert "Contract bought — $10 spent" in text


def test_prompt_bid_architecte_round2_picker_navigation(tui: TUI, run: BelAtroRun) -> None:
    run.card_enhancements["buy_contract"] = True
    run.economy.money = 10
    state = _bid_state(2)
    legal = bmain._legal_bids(state)
    r = tui.reader("enter", "down", "down", "up", "enter", "space")
    assert _cb(run, r).prompt_bid(state) == legal[1]
    assert run.economy.money == 0
    assert "Tout Atout" in tui.text and "Sans Atout" in tui.text


def test_prompt_bid_architecte_declined_or_cancelled(tui: TUI, run: BelAtroRun) -> None:
    run.card_enhancements["buy_contract"] = True
    run.economy.money = 30
    state = _bid_state(1)
    # Declined at the Y/N prompt, then a normal pass.
    assert _cb(run, tui.reader(raw_char("n"), "p")).prompt_bid(state) is None
    # Accepted but the picker is cancelled → falls through to the normal prompt.
    assert _cb(run, tui.reader("enter", "esc", "enter")).prompt_bid(state) == state.up_card.suit
    assert run.economy.money == 30
    # Too poor → never asked.
    run.economy.money = 5
    assert _cb(run, tui.reader("p")).prompt_bid(state) is None
    assert tui.text.count("buy the contract") == 2


# ── prompt_card ─────────────────────────────────────────────────────────────


def test_prompt_card_returns_card_after_undo_overlay_and_inventory(
    tui: TUI, run: BelAtroRun, run_keys: None
) -> None:
    state = _play_state()
    r = tui.reader("z", "i", "v", "esc", "enter")
    card, new_state = _cb(run, r).prompt_card(state)
    assert card in new_state.hand_of(Seat.SOUTH)
    assert r.exhausted
    assert not announce.is_top_hud_visible()  # I toggled it off


def test_prompt_card_inventory_overlay_is_painted(
    tui: TUI, run: BelAtroRun, run_keys: None
) -> None:
    _cb(run, tui.reader("v", "esc", "enter")).prompt_card(_play_state())
    assert "Trust:" in tui.text  # HUD hook repainted after each frame
    assert "Ante:" in tui.text or f"A{run.ante_number}/8" in tui.text


def test_prompt_card_quit_raises(tui: TUI, run: BelAtroRun) -> None:
    with pytest.raises(KeyboardInterrupt):
        _cb(run, tui.reader("q")).prompt_card(_play_state())


# ── other callbacks ─────────────────────────────────────────────────────────


def test_on_card_played_shows_last_completed_trick(tui: TUI, run: BelAtroRun) -> None:
    trick = tuple(
        TrickCard(seat, Card(Suit.HEARTS, rank))
        for seat, rank in zip(Seat, (Rank.ACE, Rank.KING, Rank.QUEEN, Rank.JACK), strict=True)
    )
    state = replace(_play_state(), current_trick=(), completed_tricks=(trick,))
    cb = _cb(run, tui.reader())
    cb.on_card_played(state, Seat.WEST, trick[-1].card)
    cb.on_round_end(object())
    cb.on_trick_end(state, Seat.SOUTH, 30)
    assert "Trust:" in tui.text


def test_on_redeal_banner(tui: TUI, run: BelAtroRun) -> None:
    _cb(run, tui.reader("space")).on_redeal(_bid_state())
    assert "Everyone passed — redeal" in tui.text


def test_prompt_coinche_only_under_le_tournoi(tui: TUI, run: BelAtroRun) -> None:
    r = tui.reader(raw_char("y"))
    assert _cb(run, r).prompt_coinche(_bid_state(), Seat.EAST) is False
    assert r.reads == 0
    run.card_enhancements["always_offer_coinche"] = True
    assert _cb(run, r).prompt_coinche(_bid_state(), Seat.EAST) is True
    assert "East took the bid. Coinche (x2)?" in tui.text


@pytest.mark.parametrize(
    ("key", "expected"), [("y", True), ("o", True), ("n", False), ("esc", False)]
)
def test_prompt_surcoinche_yes_no(tui: TUI, run: BelAtroRun, key: str, expected: bool) -> None:
    ev = raw_char(key) if len(key) == 1 else key
    assert _cb(run, tui.reader(ev)).prompt_surcoinche(_bid_state(), Seat.WEST) is expected
    assert "West coinched! Surcoinche back?" in tui.text


def test_prompt_heist_gates_and_one_time_hint(tui: TUI, run: BelAtroRun) -> None:
    profile = Profile()
    cb = _cb(run, tui.reader("space"), profile)
    assert cb.prompt_heist(replace(_bid_state(), taker=Seat.EAST)) is False
    south = replace(_bid_state(), taker=Seat.SOUTH)
    assert cb.prompt_heist(south) is False  # interest 0 → hint only
    assert profile.seen_heist_hint is True
    assert SaveManager().load_profile().seen_heist_hint is True  # persisted
    assert "buy the La Voûte voucher" in tui.text
    tui.screen.clear()
    assert cb.prompt_heist(south) is False
    assert "La Voûte" not in tui.text  # never shown twice


def test_prompt_heist_declare_and_decline(tui: TUI, run: BelAtroRun) -> None:
    south = replace(_bid_state(), taker=Seat.SOUTH)
    cb = _cb(run, tui.reader(raw_char("y"), "space"))
    cb.acc.interest_rate = 2
    assert cb.prompt_heist(south) is True
    assert "Win trick 8 for ×3 Mult" in tui.text
    assert "DIX DE DER HEIST DECLARED" in tui.text
    cb.reader = tui.reader(raw_char("n"))
    assert cb.prompt_heist(south) is False


# ── _play_blind (real rounds) ───────────────────────────────────────────────


@pytest.mark.parametrize("seed", [0, 1, 2, 4, 5])
def test_play_blind_real_round_records_history(tui: TUI, seed: int) -> None:
    register_all_items()
    game = bmain.BelAtroGame()
    game.run = BelAtroRun(seed=seed)
    game.run.blind_index = seed % 3
    game.reader = tui.reader(default="enter")  # take every bid, play leftmost
    money_before = game.run.economy.money
    game._play_blind()
    entry = game.run.history[-1]
    assert entry.blind_label == ("Small", "Big", "Boss")[seed % 3]
    assert entry.status in ("WON", "FAILED", "CAPOT")
    assert entry.tricks_ns + entry.tricks_ew == 8
    assert game.run.run_over is (entry.status == "FAILED")
    assert entry.money_delta == game.run.economy.money - money_before
    if seed % 3 == 2:
        assert entry.boss_name is not None
        assert "BOSS BLIND REVEALED" in tui.text


def test_play_blind_without_run_or_reader_is_noop() -> None:
    game = bmain.BelAtroGame()
    game._play_blind()  # neither set
    game.run = BelAtroRun(seed=1)
    game._play_blind()  # reader still None
    assert game.run.history == []


# ── phase helpers ───────────────────────────────────────────────────────────


def test_pick_boss_rules(tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch) -> None:
    r = tui.reader(default=None)
    run.blind_index = 0
    assert bmain.BelAtroGame._pick_boss(run, r) is None
    run.blind_index = 2
    run.card_enhancements["disable_next_boss"] = True
    assert bmain.BelAtroGame._pick_boss(run, r) is None
    assert "disable_next_boss" not in run.card_enhancements
    assert "BOSS BLIND" not in tui.text  # no reveal for the skipped boss
    # Le Joueur deck: extra boss on the Big Blind of even antes.
    run.blind_index, run.ante_number = 1, 2
    run.card_enhancements["boss_every_2"] = True
    boss = bmain.BelAtroGame._pick_boss(run, r)
    assert boss is not None
    assert boss.name.upper() in tui.text


def test_pick_boss_endless_avoids_recent(tui: TUI, run: BelAtroRun) -> None:
    from belote.belatro.run.boss import ALL_BOSS_MODIFIERS

    run.blind_index = 2
    run.endless = True
    recent_ids = [cls().id for cls in ALL_BOSS_MODIFIERS[:2]]
    seen: set[str] = set()
    for _ in range(10):
        run._recent_boss_ids[:] = recent_ids
        boss = bmain.BelAtroGame._pick_boss(run, tui.reader(default=None))
        assert boss is not None
        seen.add(boss.id)
        assert len(run._recent_boss_ids) == 2
    assert not seen & set(recent_ids)


def test_roll_ante_theme_sets_and_clears_flags(
    run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.belatro.run import ante_themes

    monkeypatch.setattr(ante_themes, "roll_theme", lambda v: ante_themes.THEME_BY_ID["tournoi"]())
    bmain.BelAtroGame._roll_ante_theme(run)
    assert run.ante_theme == "tournoi"
    assert run.card_enhancements.get("always_offer_coinche") is True
    monkeypatch.setattr(ante_themes, "roll_theme", lambda v: None)
    bmain.BelAtroGame._roll_ante_theme(run)
    assert run.ante_theme is None
    assert "always_offer_coinche" not in run.card_enhancements


def test_round_flags_surface_run_state(run: BelAtroRun) -> None:
    run.economy.money = 42
    run.tie_breaks_for_taker = True
    run.show_partner_bid_tendency = True
    run.partner_throws_trick = True
    run.agent_double_joker = True
    run.surcoinche_unlocked = True
    flags = bmain.BelAtroGame._round_flags(run)
    assert flags["current_money"] == 42
    for key in (
        "tie_breaks_for_taker",
        "traitre_active",
        "agent_double_joker_active",
        "surcoinche_unlocked",
    ):
        assert flags[key] is True
    assert str(flags["partner_bid_tendency_text"]).startswith("Partner (")
    st = as_belatro(new_game())
    st._joker_state["partner_bid_tendency_text"] = "hint!"
    assert bmain._partner_bid_hint(st) == "hint!"
    assert bmain._partner_bid_hint(as_belatro(new_game())) is None


@pytest.mark.parametrize(
    ("outcome", "needle"),
    [("won", "HEIST SECURED ×3"), ("lost", "HEIST BUSTED — tricks 1-7 forfeited (-40 chips)")],
)
def test_announce_heist_outcome(tui: TUI, outcome: str, needle: str) -> None:
    st = as_belatro(new_game())
    st._joker_state.update(heist_outcome=outcome, heist_ns_trick_chips=40)
    acc = ScoreAccumulator()
    acc.interest_rate = 2
    bmain.BelAtroGame._announce_heist_outcome(st, acc, tui.reader("space"))
    assert needle in tui.text


def test_announce_heist_outcome_silent_cases(tui: TUI) -> None:
    acc = ScoreAccumulator()
    bmain.BelAtroGame._announce_heist_outcome(as_belatro(new_game()), acc, tui.reader())
    hidden = as_belatro(new_game())
    hidden = replace(hidden, variants=replace(hidden.variants, hide_hud=True))
    hidden._joker_state["heist_outcome"] = "won"
    bmain.BelAtroGame._announce_heist_outcome(hidden, acc, tui.reader())
    assert tui.text == ""


def _bd(**kw: Any) -> Any:
    from types import SimpleNamespace

    base = {"is_failed": True, "is_capot": False, "taker_team": 0, "tricks_ns": 2, "tricks_ew": 6}
    base.update(kw)
    return SimpleNamespace(**base)


def test_settle_failed_blind_capot_insurance_and_run_over(tui: TUI, run: BelAtroRun) -> None:
    game = bmain.BelAtroGame()
    game.run = run
    run.capot_insurance = True
    run.economy.money = 20
    st = as_belatro(new_game())
    st = replace(st, _bonus_money=-5)  # LePreteur-style skim reconciled on survival
    trust = run.partner.trust.value
    survived = game._settle_failed_blind(run, tui.reader("space"), st, _bd(), 50, 100, False)
    assert survived is True and not run.run_over and not run.capot_insurance
    assert run.economy.money == 15
    assert "[Assurance Capot]" in tui.text
    assert run.partner.trust.value == trust - 1
    survived = game._settle_failed_blind(run, tui.reader("space"), st, _bd(), 50, 100, True)
    assert survived is False and run.run_over
    assert "RUN OVER — Failed to meet target 100 (scored 50)." in tui.text
    assert run.partner.trust.value == trust - 1  # lock_trust: unchanged


def test_settle_won_blind_bonuses(run: BelAtroRun) -> None:
    game = bmain.BelAtroGame()
    game.run = run
    run.gold_seal_aces = True
    run.ante_theme = "tournoi"
    aces = tuple(
        TrickCard(seat, Card(suit, Rank.ACE if seat == Seat.SOUTH else Rank.SEVEN))
        for seat, suit in zip(Seat, (Suit.HEARTS,) * 4, strict=True)
    )
    st = replace(
        as_belatro(new_game()),
        trump=Suit.SPADES,
        contract="normal",
        completed_tricks=(aces,),
        trick_trumps=(Suit.SPADES,),
    )
    st._joker_state["puriste_triggered"] = True
    assert bmain._aces_won_by_team(st, 0) == 1
    money = run.economy.money
    trust = run.partner.trust.value
    game._settle_won_blind(
        run, st, total=400, effective_target=100, auto_coinche_active=True, lock_trust=False
    )
    assert run.economy.money > money + 1
    assert run.partner.trust.value == min(10, trust + 2)  # big margin (≥1.5x)
    trust = run.partner.trust.value
    game._settle_won_blind(
        run, st, total=110, effective_target=100, auto_coinche_active=False, lock_trust=False
    )
    assert run.partner.trust.value == min(10, trust + 1)


def test_reconcile_bonus_money_without_run_is_noop() -> None:
    game = bmain.BelAtroGame()
    game._reconcile_bonus_money(10)
    game._record_history_entry(
        ante=1,
        blind_index=0,
        target=1,
        boss=None,
        final_state=as_belatro(new_game()),
        bd=_bd(),
        total=0,
        money_delta=0,
        survived_via_insurance=False,
    )
    assert game.run is None


def test_record_history_entry_contract_labels(run: BelAtroRun) -> None:
    from belote.deck import Contract

    game = bmain.BelAtroGame()
    game.run = run
    for contract, trump, label in (
        (Contract.SANS_ATOUT, None, "SA"),
        (Contract.TOUT_ATOUT, Suit.TOUT_ATOUT, "TA"),
        ("normal", Suit.CLUBS, Suit.CLUBS.symbol),
    ):
        st = replace(as_belatro(new_game()), contract=contract, trump=trump, taker=Seat.WEST)
        game._record_history_entry(
            ante=1, blind_index=7, target=10, boss=None, final_state=st, bd=_bd(is_failed=False),
            total=5, money_delta=0, survived_via_insurance=True,
        )  # fmt: skip
        e = run.history[-1]
        assert (e.contract, e.taker_label, e.blind_label, e.status) == (
            label,
            "W (EW)",
            "?",
            "SURVIVED",
        )


# ── run loop ────────────────────────────────────────────────────────────────


def _loop_game(tui: TUI, run: BelAtroRun, *script: Any) -> bmain.BelAtroGame:
    """Banners time out on their own (idle_timeouts), so the script only
    feeds the blocking prompts: shop exits and Y/N answers."""
    game = bmain.BelAtroGame()
    game.run = run
    game.reader = tui.reader(*script, idle_timeouts=True)
    return game


def test_run_loop_blind_shop_advance_until_failure(
    tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    blinds: list[tuple[int, int]] = []

    def fake_blind() -> None:
        blinds.append((run.ante_number, run.blind_index))
        if len(blinds) == 3:
            run.run_over = True

    game = _loop_game(tui, run, "esc", "esc")  # leave the shop twice
    monkeypatch.setattr(game, "_play_blind", fake_blind)
    game.unlock_tracker.pending_announcements.append("Unlocked: Something")
    game._run_loop()
    assert blinds == [(1, 0), (1, 1), (1, 2)]
    assert "=== THE SHOP ===" in tui.text
    assert "Unlocked: Something" in tui.text


def test_run_loop_victory_offers_endless(
    tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def fake_blind() -> None:
        calls.append(run.ante_number)
        if len(calls) == 2:
            run.run_over = True

    run.ante_number, run.blind_index = 8, 2
    # shop Esc → (unlock + YOU WON banners) → endless? y → next blind fails.
    game = _loop_game(tui, run, "esc", raw_char("y"))
    monkeypatch.setattr(game, "_play_blind", fake_blind)
    game._run_loop()
    assert run.endless is True
    assert len(calls) == 2
    assert "YOU WON!" in tui.text
    assert "Continue into Endless Mode?" in tui.text


def test_run_loop_victory_decline_endless_ends_run(
    tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run.ante_number, run.blind_index = 8, 2
    game = _loop_game(tui, run, "esc", raw_char("n"))
    monkeypatch.setattr(game, "_play_blind", lambda: None)
    game._run_loop()
    assert run.run_won and not run.endless


def test_run_loop_daily_victory_skips_endless_offer(
    tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    run.ante_number, run.blind_index = 8, 2
    run.daily = True
    game = _loop_game(tui, run, "esc")
    monkeypatch.setattr(game, "_play_blind", lambda: None)
    game._run_loop()
    assert run.run_won
    assert "Endless" not in tui.text


def test_run_loop_interrupt_ends_run(
    tui: TUI, run: BelAtroRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = _loop_game(tui, run)

    def boom() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(game, "_play_blind", boom)
    game._run_loop()
    assert run.run_over
    game.run = None
    game._run_loop()  # no run → immediate return


def test_drain_announcements_without_reader(run: BelAtroRun) -> None:
    game = bmain.BelAtroGame()
    game.unlock_tracker.pending_announcements.append("x")
    game._drain_unlock_announcements()
    assert game.unlock_tracker.pending_announcements == []


# ── start() / main() ────────────────────────────────────────────────────────


def test_start_from_menu_installs_and_clears_run_hooks(
    tui: TUI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import belote.belatro.run_summary as rs

    summaries: list[bool] = []
    monkeypatch.setattr(rs, "append_summary", lambda run, *, won: summaries.append(won))
    game = bmain.BelAtroGame()
    seen: dict[str, Any] = {}

    def fake_loop() -> None:
        seen["keys"] = set(prompts._EXTENSION_KEYS)
        seen["override"] = prompts._history_override
        assert game.run is not None
        game.run.run_over = True

    monkeypatch.setattr(game, "_run_loop", fake_loop)
    game._ghost_enabled = True
    game.start(tui.reader("enter"))  # BelAtro menu → Start Run
    assert seen["keys"] >= {Key.OVERLAY, Key.INVENTORY}
    assert seen["override"] is not None
    assert prompts._history_override is None
    assert not (prompts._EXTENSION_KEYS & set(bmain._RUN_KEYS))
    assert summaries == [False]
    # 4.11.0: a run quit before its first blind leaves no (empty) ghost.
    assert not list((tui.home / "data").rglob("ante1-*.json"))


def test_start_with_preset_run_and_menu_quit(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> None:
    import belote.belatro.run_summary as rs

    monkeypatch.setattr(rs, "append_summary", lambda run, *, won: None)
    game = bmain.BelAtroGame()
    preset = BelAtroRun(seed=9)
    loops: list[BelAtroRun | None] = []
    monkeypatch.setattr(game, "_run_loop", lambda: loops.append(game.run))
    game.start(tui.reader(), run=preset)
    assert loops == [preset]
    game2 = bmain.BelAtroGame()
    game2.start(tui.reader("esc"))  # menu → Esc → no run
    assert game2.run is None


def test_belatro_entry_point(tui: TUI, monkeypatch: pytest.MonkeyPatch) -> None:
    import belote.input as inp
    from belote.ansi import alt_screen_off, alt_screen_on

    r = ScriptedReader("esc")
    monkeypatch.setattr(inp, "KeyReader", lambda: r)
    monkeypatch.setattr(sys, "argv", ["belatro"])
    bmain.main()
    raw = tui.screen.raw
    assert raw.index(alt_screen_on()) < raw.rindex(alt_screen_off())
    assert r._restored and r.entered == 1
    assert "Start Run" in tui.text


def test_belatro_entry_point_version(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["belatro", "--version"])
    with pytest.raises(SystemExit):
        bmain.main()
    assert capsys.readouterr().out.startswith("belatro ")
