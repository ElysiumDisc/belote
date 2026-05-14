from __future__ import annotations

import dataclasses
from typing import Any

from belote.game import BossModifiers, GameState

# Derived from BossModifiers so new flags added there are picked up
# automatically; previously this was a hardcoded set that silently no-op'd
# any new boss field not added here in lockstep.
_BOSS_FIELDS: frozenset[str] = frozenset(f.name for f in dataclasses.fields(BossModifiers))


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

        3.6.0 (audit M3): narrowed the leading-underscore guard so it only
        rejects `_X` where `X` is an actual BossModifiers field name — the
        precise anti-pattern. Legitimate GameState scalars like `_chips`,
        `_mult`, `_joker_state`, `_rng` are now patchable through this
        proxy, which a future joker / boss effect may need.
        """
        if attr.startswith("_") and attr[1:] in _BOSS_FIELDS:
            raise ValueError(
                f"patch() received leading-underscore boss attr {attr!r}; the "
                "3.0.x shim was removed in 3.1.0 — use the unprefixed boss "
                f"field name ({attr[1:]!r})."
            )

        if attr in _BOSS_FIELDS:
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
