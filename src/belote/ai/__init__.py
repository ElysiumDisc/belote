"""Computer players. 4.11.0: split by difficulty tier into a package.

`AIPlayer(seat, difficulty)` is the only entry point callers need; the tiers
are mixins over `AIBase` (memory + void/signal tracking):

    base.py    Difficulty, AIMemory, AIBase
    easy.py    EasyMixin    — random-ish play, shallow bids
    medium.py  MediumMixin  — point-count bids, trick-winning play
    hard.py    HardMixin    — scored play strategies, signals, full memory
    player.py  AIPlayer     — dispatches each decision to its tier
"""

from __future__ import annotations

from .base import AIBase, AIMemory, Difficulty
from .player import AIPlayer

__all__ = ["AIBase", "AIMemory", "AIPlayer", "Difficulty"]
