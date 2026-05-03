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
        if attr.startswith("_"):
            # Strip leading underscore if it was from the old system
            attr = attr[1:]
        
        # We'll treat all these flat patches as boss_modifiers fields
        boss_fields = {
            "no_belote", "dynamic_trump", "no_consecutive_team_wins", "seven_eight_trump",
            "invert_scoring", "kings_zero", "auto_coinche", "queen_spades_penalty",
            "hide_hud", "ban_clubs", "no_dix_de_der", "tens_zero", "hide_partner_hand",
            "agent_double_active", "partner_forced_pass", "lock_trust_zero", "separate_scoring"
        }
        
        if attr in boss_fields:
            current_bm = self.boss_modifiers
            from belote.game import replace
            new_bm = replace(current_bm, **{attr: value})
            object.__getattribute__(self, "_patches")["boss_modifiers"] = new_bm
        else:
            object.__getattribute__(self, "_patches")[attr] = value

    def patch_card_points(self, override: dict[tuple[Suit, Rank], int]) -> None:
        """Override card point values (e.g. Kings → 0, 10s → 0)."""
        object.__getattribute__(self, "_patches")["_card_pt_override"] = override

    # ── Transparent proxy ───────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        patches = object.__getattribute__(self, "_patches")
        if name in patches:
            return patches[name]
        
        # Backward compatibility for old underscored names
        if name.startswith("_"):
            stripped = name[1:]
            if hasattr(self.boss_modifiers, stripped):
                return getattr(self.boss_modifiers, stripped)

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
