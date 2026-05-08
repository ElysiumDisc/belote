from __future__ import annotations

from typing import Any

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
        """Override a specific attribute for this round.

        Boss field names are unprefixed (e.g. "no_belote", not "_no_belote").
        The 3.0.x backward-compat shim that stripped a leading underscore was
        removed in 3.1.0 — call sites in `run/boss.py` were rewritten in lock-
        step. The `getattr(state, "_X", False)` reading anti-pattern is locked
        against in tests/belatro/test_boss_modifiers_integration.py
        `test_invariant_no_underscore_boss_attrs`.
        """
        assert not attr.startswith("_"), (
            f"patch() received leading-underscore attr {attr!r}; the 3.0.x shim "
            "was removed in 3.1.0 — use the unprefixed boss field name."
        )

        # We'll treat all these flat patches as boss_modifiers fields
        boss_fields = {
            "no_belote", "dynamic_trump", "no_consecutive_team_wins", "seven_eight_trump",
            "invert_scoring", "kings_zero", "auto_coinche", "queen_spades_penalty",
            "hide_hud", "ban_clubs", "no_dix_de_der", "tens_zero", "hide_partner_hand",
            "agent_double_active", "agent_double_late_only", "partner_forced_pass",
            "lock_trust_zero", "separate_scoring",
            "aces_zero", "jacks_zero", "declarations_zero",
        }

        if attr in boss_fields:
            current_bm = self.boss_modifiers
            from belote.game import replace
            new_bm = replace(current_bm, **{attr: value})
            object.__getattribute__(self, "_patches")["boss_modifiers"] = new_bm
        else:
            object.__getattribute__(self, "_patches")[attr] = value

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
