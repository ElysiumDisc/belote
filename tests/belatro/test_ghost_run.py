"""3.0.0 ghost-run recording tests."""

from __future__ import annotations

import json
from pathlib import Path

from belote.belatro.ghost_run import GhostRecorder, list_ghosts


def test_recorder_accumulates_events_in_order() -> None:
    rec = GhostRecorder(seed=42, deck_id="classique")
    rec.note_bid("south", "hearts", "normal")
    rec.note_play(1, "south", "J♥")
    rec.note_play(1, "west", "7♥")
    types = [e["type"] for e in rec.events]
    assert types == ["bid", "play", "play"]


def test_recorder_save_writes_valid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    rec = GhostRecorder(seed=99, deck_id="republicain")
    rec.note_bid("south", "spades", "normal")
    rec.note_play(1, "south", "A♠")
    rec.note_round_end({"taker_total": 162, "is_capot": False})

    path = rec.save("test_label")
    assert path.exists()
    with path.open() as f:
        data = json.load(f)
    assert data["seed"] == 99
    assert data["deck_id"] == "republicain"
    assert data["version"] == 1
    assert len(data["events"]) == 3


def test_list_ghosts_returns_saved_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    rec = GhostRecorder(seed=7, deck_id="classique")
    rec.note_bid("south", None, "normal")
    rec.save("alpha")
    rec2 = GhostRecorder(seed=8, deck_id="classique")
    rec2.note_bid("south", None, "normal")
    rec2.save("beta")
    ghosts = list_ghosts()
    assert len(ghosts) >= 2
    names = [g.name for g in ghosts]
    assert any("alpha" in n for n in names)
    assert any("beta" in n for n in names)
