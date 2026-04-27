from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from .game import GameState, Seat, Suit, Card, Rank

@dataclass
class Replay:
    seed: int | None
    target: int
    difficulty: dict[str, str]  # Seat name -> difficulty
    mode: str
    moves: list[dict]  # list of action dicts: {"type": "bid"|"play", "player": seat, "value": ...}

def save_replay(replay: Replay, file_path: Path) -> None:
    try:
        with open(file_path, "w") as f:
            json.dump(asdict(replay), f, indent=2)
    except OSError:
        pass

def load_replay(file_path: Path) -> Replay | None:
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            return Replay(**data)
    except (json.JSONDecodeError, OSError, TypeError):
        return None
