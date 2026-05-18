"""4.6.2 — RoundLedger.

A mutable side-channel that lives for one BelAtro round and replaces the
per-event `dataclasses.replace(GameState, ...)` pattern in
`ScoreAccumulator.update_state`.

Frozen-GameState contract still holds at round boundaries: `seal_round()` does
the single `replace()` that produces the final canonical state at round end.

Why this design:
- Pre-4.6.2 the accumulator did one `dataclasses.replace(state, _chips=...,
  _mult=..., _bonus_money=..., _joker_state=...)` per event (~19μs × 25 events
  ≈ 0.48ms per round, ~11% of `drive_round_ms`). The frozen invariant matters
  only at round-end (when the score is sealed); between events, mid-round
  consumers only need to see live chip/mult totals and the latest joker_state.
- `ledger.joker_state` is installed AS `state._joker_state` once at round
  start (a single `replace()`); classic-Belote read sites (ai.py, scoring.py,
  game.py) reading `state._joker_state.get(...)` see live mutations without
  any further replace. The HUD reads chip/mult/money directly off the ledger.
- The exception-safety guarantee of the pre-4.6.2 shadow-copy ("a raising
  handler doesn't leak partial joker_state mutations") is preserved via
  `transactional()`: snapshot at entry, commit on success, restore on the
  uncaught path. EventBus.emit() catches handler exceptions today and that
  path goes through `transactional()`'s restore branch.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any

from belote.game import GameState


@dataclass(slots=True)
class RoundLedger:
    """Mutable per-round accumulator state.

    Lifetime: one instance per BelAtro round, created in
    `ScoreAccumulator.trigger_round_start` and discarded after
    `seal_round()`. Not shared across rounds — a fresh ledger is built
    each round so streaks/timers that should reset (per-joker `_streak`
    keys etc.) start from a clean joker_state.
    """

    chips: int = 0
    mult: float = 1.0
    money: int = 0
    log: list[str] = field(default_factory=list)
    # Owned by the ledger AND aliased onto state._joker_state at round start
    # (same dict object). Mutating ledger.joker_state IS the canonical write
    # to state._joker_state — no replace() needed for classic reads to see
    # updates.
    joker_state: dict[str, Any] = field(default_factory=dict)

    def seal_round(self, state: GameState) -> GameState:
        """Produce the canonical sealed GameState for the end of the round.

        Single `replace()` that stamps the ledger's chips/mult/money into the
        frozen state. `joker_state` is already live on `state` (shared dict)
        so it does not need to be passed here — including it is a no-op but
        we omit it to make the cost explicit.
        """
        return replace(
            state,
            _chips=self.chips,
            _mult=self.mult,
            _bonus_money=self.money,
        )

    @contextmanager
    def transactional(self) -> Iterator[None]:
        """Snapshot joker_state at entry; commit on success, restore on exception.

        Preserves the pre-4.6.2 "raising handler doesn't leak partial joker_state
        mutations" guarantee. Cost is one shallow dict copy per event (~3μs),
        replacing the per-event `dataclasses.replace` (~19μs) → net ~16μs/event
        saved.

        chips/mult/money are restored too — joker handlers can write to all
        four ledger fields via the dispatch in scoring.py:_apply.
        """
        snap_chips = self.chips
        snap_mult = self.mult
        snap_money = self.money
        snap_log_len = len(self.log)
        snap_jstate = dict(self.joker_state)
        try:
            yield
        except BaseException:
            # Restore on any exception path (including KeyboardInterrupt) so a
            # buggy handler leaves the round in a consistent state. EventBus
            # catches handler Exceptions but a bare-except restore is cheap
            # insurance.
            self.chips = snap_chips
            self.mult = snap_mult
            self.money = snap_money
            del self.log[snap_log_len:]
            self.joker_state.clear()
            self.joker_state.update(snap_jstate)
            raise
