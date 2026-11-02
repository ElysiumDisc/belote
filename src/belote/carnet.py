"""5.0.0 — Le Carnet de Parties: your last five finished classic games, each
with a one-line verdict ("You chutéed on a 92 vs 94 — brutal").

`note_round` is fed every recorded round's breakdown (gameflow) so the
verdict can talk about the deciding round's table points, which the score
history (credited points only) doesn't keep. `record_game` builds the entry
at game over; `Statistics.recent_games` stores the newest five; the
Statistics screen shows them (`carnet_lines`).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .game import GameState
    from .scoring import ScoringBreakdown

CARNET_SIZE = 5


@dataclass(frozen=True)
class LastRound:
    """The table-level facts of a game's final round, from its breakdown."""

    ns_took: bool
    failed: bool
    capot: bool
    ns_capot: bool
    taker_pts: int  # card points + annonces + belote, before the chute rule
    defender_pts: int


_last_round: LastRound | None = None


def note_round(breakdown: ScoringBreakdown) -> None:
    """Remember the round just scored (only the last one matters)."""
    global _last_round
    taker = breakdown.table_taker_pts + breakdown.taker_declarations + breakdown.taker_belote
    defender = (
        breakdown.table_defender_pts + breakdown.defender_declarations + breakdown.defender_belote
    )
    ns_took = breakdown.taker_team == 0
    _last_round = LastRound(
        ns_took=ns_took,
        failed=breakdown.is_failed,
        capot=breakdown.is_capot,
        ns_capot=breakdown.is_capot and breakdown.tricks_ns == 8,
        taker_pts=taker,
        defender_pts=defender,
    )


def reset() -> None:
    global _last_round
    _last_round = None


def _worst_deficit(state: GameState) -> int:
    """How far behind (NS − EW, cumulative) the player ever was; ≤ 0."""
    ns = ew = 0
    worst = 0
    for rnd in state.score_history:
        ns += rnd.ns_total
        ew += rnd.ew_total
        worst = min(worst, ns - ew)
    return worst


def verdict(
    *, won: bool, ns: int, ew: int, rounds: int, deficit: int, last: LastRound | None
) -> str:
    """The one-line verdict for a finished game (pure)."""
    margin = abs(ns - ew)
    if last is not None:
        if not won and last.ns_took and last.failed and not last.capot:
            close = last.defender_pts - last.taker_pts <= 10
            tail = "brutal" if close else "it was never on"
            return f"You chutéed on a {last.taker_pts} vs {last.defender_pts} — {tail}."
        if not won and last.capot and not last.ns_capot:
            return "Capoted in the last round. Ouch."
        if won and last.ns_capot:
            return "Sealed it with a capot — magnifique."
    if won and deficit <= -200:
        return f"Came back from {-deficit} down. Never in doubt."
    if margin < 40:
        return f"Photo finish: {ns} to {ew}." if won else f"So close: {ns} to {ew}."
    if margin >= 500:
        return f"A rout: {ns} to {ew}." if won else f"Flattened, {ew} to {ns}."
    if won and rounds <= 4:
        return f"Done in {rounds} rounds. Efficient."
    if rounds >= 12:
        return f"A {rounds}-round marathon, {'won' if won else 'lost'} {ns} to {ew}."
    return f"A solid win, {ns} to {ew}." if won else f"Beaten {ew} to {ns}. Next time."


def record_game(state: GameState, *, won: bool, difficulty: str) -> dict[str, Any]:
    """The Carnet entry for a finished game (JSON-ready)."""
    ns, ew = state.team_scores
    rounds = len(state.score_history)
    entry: dict[str, Any] = {
        "date": datetime.date.today().isoformat(),
        "won": won,
        "ns": ns,
        "ew": ew,
        "rounds": rounds,
        "difficulty": difficulty,
        "verdict": verdict(
            won=won,
            ns=ns,
            ew=ew,
            rounds=rounds,
            deficit=_worst_deficit(state),
            last=_last_round,
        ),
    }
    reset()
    return entry


_ENTRY_TYPES: dict[str, type] = {
    "date": str,
    "won": bool,
    "ns": int,
    "ew": int,
    "rounds": int,
    "difficulty": str,
    "verdict": str,
}


def conform_entries(value: object) -> list[dict[str, Any]]:
    """Validate `recent_games` loaded from disk: well-formed entries only,
    newest five."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ok = all(
            isinstance(item.get(k), t) and (t is bool or not isinstance(item.get(k), bool))
            for k, t in _ENTRY_TYPES.items()
        )
        if ok:
            out.append({k: item[k] for k in _ENTRY_TYPES})
    return out[:CARNET_SIZE]


def carnet_lines(entries: list[dict[str, Any]], width: int = 76) -> list[str]:
    """Plain lines (no colour) for the Statistics screen."""
    if not entries:
        return ["  (no finished games yet)"]
    lines: list[str] = []
    for e in entries:
        try:
            day = datetime.date.fromisoformat(e["date"]).strftime("%d %b")
        except ValueError:
            day = "??"
        mark = "W" if e["won"] else "L"
        head = f"  {day}  {mark} {e['ns']}–{e['ew']}  "
        lines.append((head + e["verdict"])[:width])
    return lines
