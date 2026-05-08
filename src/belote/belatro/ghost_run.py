"""3.0.0: Ghost Run recording — capture the seed + decisions of a winning
BelAtro run so the player can re-watch it or share the JSON file.

This module only handles serialization. The actual replay viewer/playback is
out of scope for the initial 3.0.0 cut — what's saved is enough to reconstruct
the run later. The save path lives next to the regular profile file.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _ghost_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "."))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    path = base / "belote" / "ghosts"
    path.mkdir(parents=True, exist_ok=True)
    return path


class GhostRecorder:
    """Accumulates per-decision events during a run; flushes on victory.

    Usage:
        recorder = GhostRecorder(seed=12345, deck_id="republicain")
        # ... during play:
        recorder.note_bid(seat="south", trump="hearts", contract="normal")
        recorder.note_play(trick=1, seat="south", card="J♥")
        # ... on victory:
        path = recorder.save("ante8_win")
    """

    def __init__(self, seed: int, deck_id: str) -> None:
        self.seed = seed
        self.deck_id = deck_id
        self.started_at = int(time.time())
        self.events: list[dict[str, Any]] = []

    def note_bid(self, seat: str, trump: str | None, contract: str) -> None:
        self.events.append(
            {"type": "bid", "seat": seat, "trump": trump, "contract": contract}
        )

    def note_play(self, trick: int, seat: str, card: str) -> None:
        self.events.append({"type": "play", "trick": trick, "seat": seat, "card": card})

    def note_round_end(self, breakdown: dict[str, Any]) -> None:
        self.events.append({"type": "round_end", "breakdown": breakdown})

    def save(self, label: str = "run") -> Path:
        """Write the recorded events to ``<ghosts>/<label>-<seed>.json``."""
        path = _ghost_dir() / f"{label}-{self.seed}.json"
        record = {
            "version": 1,
            "seed": self.seed,
            "deck_id": self.deck_id,
            "started_at": self.started_at,
            "ended_at": int(time.time()),
            "events": self.events,
        }
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)
        except OSError:
            # Best-effort: ghost recording is non-essential.
            pass
        return path


def list_ghosts() -> list[Path]:
    """Enumerate saved ghost files. Used by a future viewer."""
    try:
        return sorted(_ghost_dir().glob("*.json"))
    except OSError:
        return []
