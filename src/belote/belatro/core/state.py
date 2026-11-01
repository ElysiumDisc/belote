"""BelAtro's round state: the core `GameState` plus the expansion's own data.

The classic engine knows nothing about chips, mult, money or joker state. It
only ever builds new states with `dataclasses.replace()`, which preserves the
concrete subclass, so a `BelatroState` handed to `play_card` / `process_bid`
/ `start_round` comes back as a `BelatroState` with its fields intact.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from belote.game import GameState

_CORE_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(GameState))


@dataclass(frozen=True, slots=True)
class BelatroState(GameState):
    # Per-round joker / deck / voucher flags. Values must be scalars
    # (bool/int/str/frozenset) — see tests/belatro/test_phase1_plumbing.py
    # `test_joker_state_only_contains_scalar_values`.
    #
    # Mutable dict inside a frozen dataclass, by design (4.8.2 B4): from
    # `ScoreAccumulator.trigger_round_start` onward this dict IS
    # `acc._ledger.joker_state`. The round driver mutates it IN PLACE (heist
    # declaration, ...) to keep that alias; `replace(state, _joker_state={...})`
    # would copy the dict and make later ledger writes invisible to readers.
    _joker_state: dict[str, object] = field(default_factory=dict)
    _chips: int = 0
    _mult: float = 1.0
    _bonus_money: int = 0


def as_belatro(state: GameState) -> BelatroState:
    """Return `state` as a BelatroState (no-op if it already is one)."""
    if isinstance(state, BelatroState):
        return state
    return BelatroState(**{name: getattr(state, name) for name in _CORE_FIELDS})


def joker_flag(state: GameState, key: str) -> object:
    """Read a BelAtro joker_state flag from any state (None on classic states)."""
    if isinstance(state, BelatroState):
        return state._joker_state.get(key)
    return None
