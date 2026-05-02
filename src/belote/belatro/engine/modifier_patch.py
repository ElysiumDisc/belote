from __future__ import annotations

from typing import Any

from belote.deck import Rank, Suit
from belote.game import GameState


class PatchedGameState:
    """
    Thin proxy around a classic GameState.
    BossModifiers register patches; everything else falls through untouched.
    """

    def __init__(self, state: GameState) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_patches", {})

    # ── Patch registration ──────────────────────────────────────────────

    def patch(self, attr: str, value: Any) -> None:
        """Override a specific attribute for this round."""
        object.__getattribute__(self, "_patches")[attr] = value

    def patch_card_points(self, override: dict[tuple[Suit, Rank], int]) -> None:
        """Override card point values (e.g. Kings → 0, 10s → 0)."""
        object.__getattribute__(self, "_patches")["_card_pt_override"] = override

    # ── Transparent proxy ───────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        patches = object.__getattribute__(self, "_patches")
        if name in patches:
            return patches[name]
        return getattr(object.__getattribute__(self, "_state"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Writes go to patches to avoid mutating frozen _state
        if name in ("_state", "_patches"):
            object.__setattr__(self, name, value)
        else:
            self.patch(name, value)

    @property
    def raw(self) -> GameState:
        return object.__getattribute__(self, "_state")
