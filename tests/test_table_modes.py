"""4.11.0: Spectate and Hot-seat — real rounds through `gameflow.run_round`
with the table modes from `belote.table_modes`."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any

import pytest

from belote import a11y
from belote import gameflow as gf
from belote.ai import AIPlayer, Difficulty
from belote.game import GameState, Phase, Seat, legal_bids, legal_cards, new_game
from belote.input import Key, KeyEvent, char_event
from belote.table_modes import (
    HOTSEAT_PRESETS,
    SOLO,
    PaceControl,
    SpectatorReader,
    TableMode,
    consumed,
    hotseat,
    spectate,
)
from belote.ui import spectate as spectate_ui
from tests.harness import TUI, ScriptedReader


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Stub every animation/screen call; record the ones the modes care about."""
    seen: dict[str, list[Any]] = {"display": [], "stats": [], "pass": [], "preview": []}

    def nothing(*_a: object, **_k: object) -> None:
        return None

    for name in (
        "patch_trick_card",
        "slide_card_to_table_hint",
        "pulse_winner_glow",
        "animate_score_update",
        "announce",
        "belote_stinger",
        "achievement_toast",
    ):
        monkeypatch.setattr(gf, name, nothing)
    monkeypatch.setattr(gf, "display", lambda s, *_a, **_k: seen["display"].append(s))
    monkeypatch.setattr(gf, "show_hand_preview", lambda *_a: seen["preview"].append(1))
    monkeypatch.setattr(gf, "interruptible_sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(gf, "show_round_summary", lambda *_a, **_k: True)
    monkeypatch.setattr(gf, "update_stats_round", lambda *a, **_k: seen["stats"].append(a) or [])
    monkeypatch.setattr(
        gf, "pass_device_screen", lambda _r, seat, _n: seen["pass"].append(seat) or True
    )
    monkeypatch.setattr(a11y, "speak", nothing)
    return seen


def _ais(seats: set[Seat], seed: int) -> dict[Seat, AIPlayer]:
    return {s: AIPlayer(s, Difficulty.MEDIUM, rng=random.Random(seed + s.value)) for s in seats}


def _no_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("a spectated round must never prompt")

    for name in ("prompt_bid", "prompt_card", "prompt_coinche", "prompt_surcoinche"):
        monkeypatch.setattr(gf, name, boom)


# ── Spectate ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", range(5))
def test_spectate_round_plays_itself_without_prompts_or_stats(
    quiet: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    _no_prompts(monkeypatch)
    mode = spectate()
    assert mode.pace is not None
    reader = SpectatorReader(ScriptedReader().as_reader(), mode.pace)
    state = new_game()
    for rnd in range(3):
        res = gf.run_round(
            state, reader, _ais(set(Seat), seed), 0, 0, 0, [], random.Random(seed * 9 + rnd), mode
        )
        assert res is not None and res.phase in (Phase.DEAL, Phase.GAME_OVER)
        state = res
    assert sum(state.team_scores) > 0
    assert quiet["stats"] == [] and quiet["preview"] == []


def test_spectate_quit_key_stops_the_round(quiet: dict[str, list[Any]], monkeypatch) -> None:
    _no_prompts(monkeypatch)
    mode = spectate()
    assert mode.pace is not None
    mode.pace.quit = True  # Q was pressed during an animation
    reader = SpectatorReader(ScriptedReader().as_reader(), mode.pace)
    assert gf.run_round(new_game(), reader, _ais(set(Seat), 1), 0, 0, 0, [], None, mode) is None


def test_spectator_reader_speed_pause_quit() -> None:
    pace = PaceControl()
    inner = ScriptedReader(char_event("+"), char_event("+"), char_event("-"), KeyEvent(Key.SPACE),
                           Key.ENTER, char_event("x"), Key.QUIT)  # fmt: skip
    r = SpectatorReader(inner.as_reader(), pace)
    start = pace.step
    assert consumed(r.read()) and pace.step == start + 1
    assert consumed(r.read()) and pace.step == start + 2
    assert consumed(r.read()) and pace.step == start + 1
    assert consumed(r.read())  # Space → paused until Enter (consumed inside)
    assert r.read() == char_event("x")  # ordinary keys pass through
    assert r.read().key == Key.QUIT and pace.quit


def test_pace_steps_are_clamped_and_scale_delays() -> None:
    pace = PaceControl()
    for _ in range(20):
        pace.faster()
    assert pace.scale == 0 and pace.label == "max"
    for _ in range(20):
        pace.slower()
    assert pace.scale == 2.0
    policy = gf.ClassicRound(None, {}, 0.5, 1.0, [], mode=TableMode(frozenset(), pace=pace))  # type: ignore[arg-type]
    assert policy.ai_delay == 1.0 and policy.trick_pause == 2.0


def test_streak_scoring_and_persistence(tui: TUI) -> None:
    st = spectate_ui.Streak()
    assert st.record(0, 0) is True and st.record(1, 1) is True
    assert (st.current, st.best) == (2, 2)
    assert st.record(0, 1) is False and st.current == 0 and st.best == 2
    assert st.record(None, 0) is None and st.record(0, None) is None
    assert st.guesses == 3 and st.correct == 2
    spectate_ui.save_best(st.best)
    assert spectate_ui.load_best() == 2


def test_round_winner() -> None:
    a = replace(new_game(), team_scores=(100, 100))
    assert spectate_ui.round_winner(a, replace(a, team_scores=(200, 120))) == 0
    assert spectate_ui.round_winner(a, replace(a, team_scores=(110, 262))) == 1
    assert spectate_ui.round_winner(a, a) is None


@pytest.mark.parametrize(
    ("keys", "expected"),
    [(("left",), 0), (("right",), 1), (("enter",), -1), (("q",), "QUIT"), ((), "QUIT")],
)
def test_ask_prediction(tui: TUI, keys: tuple[str, ...], expected: object) -> None:
    got = spectate_ui.ask_prediction(tui.reader(*keys).as_reader(), 3, spectate_ui.Streak(), "×1.0")
    assert got == expected
    assert "Who takes this round?" in tui.text


# ── Hot-seat ────────────────────────────────────────────────────────────────


def _hotseat_prompts(monkeypatch: pytest.MonkeyPatch, rng: random.Random) -> list[GameState]:
    """Humans pick random legal moves; record the (rotated) views the card
    prompt saw."""
    views: list[GameState] = []

    def prompt_bid(view: GameState, _r: object) -> object:
        return rng.choice(legal_bids(view))

    def prompt_card(view: GameState, _r: object, **_k: object) -> tuple[object, GameState]:
        views.append(view)
        return rng.choice(legal_cards(view, Seat.SOUTH)), view

    monkeypatch.setattr(gf, "prompt_bid", prompt_bid)
    monkeypatch.setattr(gf, "prompt_card", prompt_card)
    monkeypatch.setattr(gf, "prompt_coinche", lambda view, _r: False)
    monkeypatch.setattr(gf, "prompt_surcoinche", lambda *_a: False)
    return views


@pytest.mark.parametrize("preset", range(len(HOTSEAT_PRESETS)))
@pytest.mark.parametrize("seed", range(3))
def test_hotseat_each_human_sees_only_their_own_hand(
    quiet: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch, preset: int, seed: int
) -> None:
    humans = HOTSEAT_PRESETS[preset][1]
    mode = hotseat(humans)
    views = _hotseat_prompts(monkeypatch, random.Random(seed))
    real_hands: list[tuple[Seat, GameState]] = []
    real_choose_card = gf.ClassicRound.choose_card

    def spy(self: gf.ClassicRound, state: GameState, seat: Seat) -> Any:
        if seat in humans:
            real_hands.append((seat, state))
        return real_choose_card(self, state, seat)

    monkeypatch.setattr(gf.ClassicRound, "choose_card", spy)
    tagged: set[int] = set()
    viewers: set[Seat] = set()
    real_view = gf.ClassicRound._view

    def view_spy(self: gf.ClassicRound, state: GameState) -> GameState:
        assert self.viewer is not None, "drew the table before anyone held the device"
        viewers.add(self.viewer)
        out = real_view(self, state)
        tagged.add(id(out))
        return out

    monkeypatch.setattr(gf.ClassicRound, "_view", view_spy)
    ais = _ais(set(Seat) - humans, seed)
    res = gf.run_round(new_game(), None, ais, 0, 0, 0, [], random.Random(seed), mode)  # type: ignore[arg-type]
    assert res is not None
    assert quiet["stats"] == [] and quiet["preview"] == []
    # The device is passed whenever a different human must act...
    assert quiet["pass"], "the first human must be handed the device"
    assert all(a != b for a, b in zip(quiet["pass"], quiet["pass"][1:], strict=False))
    # ...and every card prompt showed the acting human's hand at the bottom.
    for (seat, real), view in zip(real_hands, views, strict=True):
        assert view.hand_of(Seat.SOUTH) == real.hand_of(seat)
    # Privacy: every frame drawn went through the policy's `_view` while a
    # human held the device (a raw `display(state)` would show SOUTH's hand
    # to whoever is holding it).
    assert quiet["display"]
    assert all(id(f) in tagged for f in quiet["display"])
    assert viewers and viewers <= humans


def test_hotseat_undo_is_ignored(quiet: dict[str, list[Any]], monkeypatch) -> None:
    mode = hotseat(frozenset({Seat.SOUTH, Seat.NORTH}))
    rng = random.Random(4)
    calls = {"n": 0}

    def prompt_card(view: GameState, _r: object, **_k: object) -> tuple[object, GameState]:
        calls["n"] += 1
        if calls["n"] == 1:
            return "UNDO", view  # ignored: re-prompt instead of rewinding
        return rng.choice(legal_cards(view, Seat.SOUTH)), view

    _hotseat_prompts(monkeypatch, rng)
    monkeypatch.setattr(gf, "prompt_card", prompt_card)
    ais = _ais({Seat.EAST, Seat.WEST}, 4)
    res = gf.run_round(new_game(), None, ais, 0, 0, 0, [], random.Random(4), mode)  # type: ignore[arg-type]
    assert res is not None and calls["n"] >= 9  # 8 cards + the ignored undo


def test_hotseat_quit_on_pass_screen(quiet: dict[str, list[Any]], monkeypatch) -> None:
    monkeypatch.setattr(gf, "pass_device_screen", lambda *_a: False)
    mode = hotseat(frozenset(Seat))
    assert gf.run_round(new_game(), None, {}, 0, 0, 0, [], random.Random(1), mode) is None  # type: ignore[arg-type]


def test_hotseat_rejects_bad_seat_counts() -> None:
    with pytest.raises(ValueError):
        hotseat(frozenset({Seat.SOUTH}))
    assert SOLO.is_solo and SOLO.records_stats
    assert not spectate().records_stats


def test_pass_device_screen(tui: TUI) -> None:
    from belote.table_modes import pass_device_screen

    assert pass_device_screen(tui.reader("x", "enter").as_reader(), Seat.EAST, 3) is True
    assert "EAST" in tui.text.upper() and "look away" in tui.text
    assert pass_device_screen(tui.reader("q").as_reader(), Seat.WEST, 2) is False


# ── main menu wiring ────────────────────────────────────────────────────────


def test_choose_table_mode(tui: TUI) -> None:
    from belote import main as main_mod

    m = main_mod._choose_table_mode(tui.reader("enter").as_reader())
    assert m is not None and m.pace is not None and not m.humans
    m = main_mod._choose_table_mode(tui.reader("down", "down", "enter").as_reader())
    assert m is not None and m.hotseat and m.humans == HOTSEAT_PRESETS[1][1]
    assert main_mod._choose_table_mode(tui.reader("esc").as_reader()) is None


def test_spectate_game_loop_scores_predictions(tui: TUI, monkeypatch) -> None:
    from belote import main as main_mod
    from belote import settings as settings_mod

    rounds = [
        replace(new_game(), phase=Phase.DEAL, team_scores=(120, 42)),
        replace(new_game(), phase=Phase.GAME_OVER, team_scores=(1010, 300)),
    ]
    seen_modes: list[TableMode] = []

    def fake_round(state: GameState, reader: Any, ais: dict, *a: Any) -> GameState:
        seen_modes.append(a[-1])
        assert set(ais) == set(Seat)  # four AIs
        return rounds.pop(0)

    monkeypatch.setattr(main_mod, "run_round", fake_round)
    monkeypatch.setattr(main_mod, "_record_game_over", lambda *a: pytest.fail("no stats"))
    monkeypatch.setattr(main_mod, "announce", lambda *a, **k: None)
    # Predict NS twice (both right), then Enter on the game-over screen.
    reader = tui.reader("left", "left", "enter")
    main_mod._play_classic_game(reader.as_reader(), settings_mod.Settings(), 3, spectate())
    assert all(m.pace is not None for m in seen_modes)
    assert spectate_ui.load_best() == 2
