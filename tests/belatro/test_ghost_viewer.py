"""4.11.0 ghost runs: the v2 recorder (shop / boss / round results), v1
backward compatibility, round reconstruction from seed + plays, and the
"Watch Ghost Run" viewer driven headlessly."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from belote.belatro import main as bmain
from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.ghost_run import (
    GHOST_VERSION,
    GhostRecorder,
    ghost_from_dict,
    load_all_ghosts,
    load_ghost,
    parse_card,
    split_rounds,
)
from belote.belatro.ui.ghost_viewer import (
    ReplayControl,
    control_action,
    picker_lines,
    replay_frames,
    round_base,
    round_summary_lines,
    show_ghost_picker,
    watch_ghost,
)
from belote.game import Seat
from belote.input import Key, KeyEvent
from tests.harness import ScriptedReader, strip_ansi

_RECORD: dict[str, Any] = {}


def _record_ghost(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Play 3 real blinds (AI South) with the recorder on; cache the JSON."""
    if _RECORD:
        return _RECORD
    from belote.ai import AIPlayer, Difficulty
    from belote.belatro.items.tarots import LeChariot

    ai = AIPlayer(Seat.SOUTH, Difficulty.MEDIUM, rng=random.Random(1))
    monkeypatch.setattr(bmain.UICallbacks, "prompt_bid", lambda self, s: ai.decide_bid(s))
    monkeypatch.setattr(bmain.UICallbacks, "prompt_card", lambda self, s: (ai.decide_card(s), s))
    monkeypatch.setattr(bmain.UICallbacks, "prompt_heist", lambda self, s: False)
    monkeypatch.setattr(bmain.UICallbacks, "prompt_surcoinche", lambda self, s, c: False)
    monkeypatch.setattr(bmain.UICallbacks, "on_trick_end", lambda self, s, w, p: None)
    monkeypatch.setattr(bmain.UICallbacks, "on_card_played", lambda self, s, seat, c: None)
    game = bmain.BelAtroGame()
    game.reader = ScriptedReader(idle_timeouts=True, max_reads=100_000)
    game.run = BelAtroRun(seed=5, profile=game.profile)
    rec = GhostRecorder(seed=5, deck_id="classique")
    rec.note_run_start(game.run)
    game.run.recorder = game._ghost_recorder = rec
    for _ in range(3):
        game._play_blind()
        if game.run.run_over:
            break
        # A tiny shop visit between blinds, through the real Shop.
        from belote.belatro.run.shop import Shop

        game.run.economy.money += 20
        shop = Shop(game.run, game.profile)
        shop.generate_inventory()
        shop.reroll()
        chariot = LeChariot()
        game.run.consumables.append(chariot)
        game.run.consume(chariot)
        game.run.advance_blind()
    rec.note_run_end(game.run, won=False)
    _RECORD.update(rec.to_record("ante1"))
    return _RECORD


@pytest.fixture
def ghost_record(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Any:
    record = _record_ghost(monkeypatch)
    capsys.readouterr()
    return json.loads(json.dumps(record))  # a JSON round-trip, like a file


# ── recorder (v2) ──────────────────────────────────────────────────────────


def test_v2_record_has_version_outcome_and_run_shape(ghost_record: dict[str, Any]) -> None:
    assert ghost_record["version"] == GHOST_VERSION == 2
    assert ghost_record["format"] == "belatro-ghost"
    assert ghost_record["outcome"]["rounds"] >= 1
    types = [e["type"] for e in ghost_record["events"]]
    assert types[0] == "run_start" and types[-1] == "run_end"
    for kind in ("round_start", "bid", "play", "round_end", "round_result", "reroll", "use"):
        assert kind in types, kind
    starts = [e for e in ghost_record["events"] if e["type"] == "round_start"]
    assert starts[0]["blind"] == 0 and isinstance(starts[0]["round_seed"], int)
    if len(starts) == 3:
        assert starts[2]["boss"] is not None  # the boss blind records its boss
    result = next(e for e in ghost_record["events"] if e["type"] == "round_result")
    assert len(result["winners"]) == 8 and len(result["trick_points"]) == 8


def test_recorder_notes_buy_and_sell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from belote.belatro.items.jokers.tempo import LeCapitaine
    from belote.belatro.progression.save import Profile
    from belote.belatro.run.shop import Shop

    run = BelAtroRun(seed=1)
    rec = GhostRecorder(seed=1, deck_id="classique")
    run.recorder = rec
    run.economy.money = 50
    shop = Shop(run, Profile())
    shop.inventory = [LeCapitaine()]
    assert shop.buy_item(0)
    shop.sell_joker(0)
    kinds = [(e["type"], e.get("id")) for e in rec.events]
    assert kinds == [("buy", "le_capitaine"), ("sell", "le_capitaine")]
    assert rec.events[0]["kind"] == "joker" and rec.events[0]["cost"] == LeCapitaine.cost


def test_recorder_notes_jokers_granted_by_tarots() -> None:
    from belote.belatro.items.tarots import LeJugement

    run = BelAtroRun(seed=3)
    rec = GhostRecorder(seed=3, deck_id="classique")
    run.recorder = rec
    run.consume(LeJugement())
    assert [e["type"] for e in rec.events] == ["use", "acquire"]
    assert rec.events[1]["source"] == "le_jugement"


# ── reader ─────────────────────────────────────────────────────────────────


def test_v1_files_still_load(tmp_path: Path) -> None:
    v1 = {
        "version": 1,
        "seed": 7,
        "deck_id": "classique",
        "started_at": 1,
        "ended_at": 2,
        "events": [
            {"type": "bid", "seat": "south", "trump": "hearts", "contract": "normal"},
            {"type": "play", "trick": 1, "seat": "south", "card": "J♥"},
            {"type": "round_end", "breakdown": {"taker_total": 90}},
            {"type": "bid", "seat": "east", "trump": None, "contract": "normal"},
            {"type": "round_end", "breakdown": {}},
        ],
    }
    path = tmp_path / "won-7-1.json"
    path.write_text(json.dumps(v1))
    ghost = load_ghost(path)
    assert ghost is not None and ghost.version == 1 and ghost.label == "won"
    assert len(ghost.rounds) == 2
    assert ghost.rounds[0].plays[0][2] == parse_card("J♥")
    assert "v1" in ghost.summary


@pytest.mark.parametrize("content", ["not json", "[]", '{"events": 3}', '{"seed": 1}'])
def test_unreadable_files_are_skipped(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content)
    assert load_ghost(path) is None


def test_parse_card_round_trips_every_card() -> None:
    from belote.deck import make_deck

    for c in make_deck():
        assert parse_card(repr(c)) == c
    assert parse_card("Z♥") is None and parse_card("") is None


def test_final_bids_drop_an_all_pass_deal() -> None:
    events = [
        {"type": "bid", "seat": s, "trump": None, "contract": "normal"}
        for s in ["east", "north", "west", "south"] * 2
    ]
    events.append({"type": "bid", "seat": "north", "trump": "spades", "contract": "normal"})
    (rnd,) = split_rounds(events)
    assert len(rnd.bids) == 9 and len(rnd.final_bids()) == 1


# ── reconstruction ─────────────────────────────────────────────────────────


def test_rounds_rebuild_from_seed_and_replay_32_cards(ghost_record: dict[str, Any]) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None and ghost.rounds
    for rnd in ghost.rounds:
        built = round_base(rnd)
        assert built is not None
        _base, verified = built
        if rnd.final_bids() == rnd.bids:
            assert verified, rnd.title  # seed + bids reproduce the dealt hands
        frames = replay_frames(rnd)
        assert len(frames) == 1 + 32
        last = frames[-1].state
        assert all(len(h) == 0 for h in last.hands)
        assert len(last.current_trick) == 4
        assert sum(frames[-1].state.current_round_points) + rnd.result["trick_points"][-1] == sum(
            rnd.result["trick_points"]
        )


def test_round_with_unfinished_plays_has_no_frames() -> None:
    (rnd,) = split_rounds([{"type": "play", "trick": 1, "seat": "south", "card": "J♥"}])
    assert replay_frames(rnd) == []


def test_summary_lists_shop_activity(ghost_record: dict[str, Any]) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None
    text = strip_ansi("\n".join(round_summary_lines(ghost.rounds[0])))
    assert "target" in text and "rerolled the shop" in text and "used Le Chariot" in text


# ── viewer controls / UI ───────────────────────────────────────────────────


def test_control_action_speed_pause_skip_quit() -> None:
    ctl = ReplayControl()
    assert control_action(None, ctl) == "next"
    assert control_action(KeyEvent(Key.CHAR, "+"), ctl) == "next" and ctl.delay < 0.6
    ctl.delay = 0.6
    assert control_action(KeyEvent(Key.CHAR, "-"), ctl) == "next" and ctl.delay > 0.6
    assert control_action(KeyEvent(Key.SPACE), ctl) == "stay" and ctl.paused
    assert control_action(KeyEvent(Key.RIGHT), ctl) == "next"  # step while paused
    assert control_action(KeyEvent(Key.CHAR, "p"), ctl) == "next" and not ctl.paused
    assert control_action(KeyEvent(Key.CHAR, "n"), ctl) == "skip"
    assert control_action(KeyEvent(Key.ESC), ctl) == "quit"
    for _ in range(30):
        ctl.faster()
    assert ctl.delay == pytest.approx(0.05)


def test_watch_ghost_renders_rounds_through_the_table(
    tui: Any, ghost_record: dict[str, Any]
) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None
    reader = tui.reader(idle_timeouts=True)
    watch_ghost(ghost, reader)
    text = tui.text
    assert "GHOST" in text and "Trick 8" in text
    assert "End of the recording" in text
    # Every round was replayed (a timeout per frame + one per summary card).
    assert len(reader.timeouts) >= len(ghost.rounds) * 34


def test_watch_ghost_skip_and_quit(tui: Any, ghost_record: dict[str, Any]) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None
    # Skip round 1 at its first frame, then quit on round 2's first frame.
    reader = tui.reader("n", None, "esc")
    watch_ghost(ghost, reader)
    assert "End of the recording" not in tui.text
    assert reader.exhausted


def test_watch_ghost_pause_then_resume(tui: Any, ghost_record: dict[str, Any]) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None
    ctl = ReplayControl()
    reader = tui.reader(" ", "+", "right", " ", "esc")
    watch_ghost(ghost, reader, ctl)
    assert not ctl.paused and ctl.delay < 0.6
    assert "PAUSED" in tui.text


def test_ghost_picker_lists_and_opens(tui: Any, ghost_record: dict[str, Any]) -> None:
    from belote.belatro.ghost_run import _ghost_dir

    (_ghost_dir() / "ante1-5-1.json").write_text(json.dumps(ghost_record))
    assert len(load_all_ghosts()) == 1
    reader = tui.reader("down", "enter", "esc", "esc")
    show_ghost_picker(reader)
    text = tui.text
    assert "WATCH GHOST RUN" in text and "seed 5" in text and "GHOST" in text


def test_ghost_picker_empty_state(tui: Any) -> None:
    show_ghost_picker(tui.reader("enter", "esc"))
    assert "No ghost runs saved yet" in tui.text


@pytest.mark.parametrize(("cols", "rows"), [(80, 32), (100, 38)])
def test_picker_fits(ghost_record: dict[str, Any], cols: int, rows: int) -> None:
    ghost = ghost_from_dict(ghost_record)
    assert ghost is not None
    lines = picker_lines([ghost] * 40, 39, cols, rows - 8)
    assert len(lines) <= rows
    assert all(len(strip_ansi(line)) <= cols for line in lines)


def test_menu_entry_opens_the_viewer(tui: Any) -> None:
    from belote.belatro.progression.save import Profile
    from belote.belatro.ui.menu import BelAtroMainMenu

    menu = BelAtroMainMenu(tui.reader("down", "down", "down", "enter", "esc", "esc"), Profile())
    assert menu.run() is None
    assert "WATCH GHOST RUN" in tui.text


def test_losing_run_is_saved_with_rounds(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import belote.belatro.run_summary as rs

    monkeypatch.setattr(rs, "append_summary", lambda run, *, won: None)
    game = bmain.BelAtroGame()

    def fake_loop() -> None:
        assert game._ghost_recorder is not None and game.run is not None
        assert game.run.recorder is game._ghost_recorder
        game._ghost_recorder.rounds_played = 1  # as if a blind was played
        game.run.run_over = True

    monkeypatch.setattr(game, "_run_loop", fake_loop)
    game._ghost_enabled = True
    game.start(tui.reader("enter"))
    (path,) = list((tui.home / "data").rglob("ante1-*.json"))
    ghost = load_ghost(path)
    assert ghost is not None and ghost.outcome == {
        "won": False,
        "ante": 1,
        "blind": 0,
        "endless": False,
        "rounds": 1,
    }
