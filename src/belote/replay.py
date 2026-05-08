"""3.0.0: post-round replay analyzer for classic Belote.

Given a list of (GameState, chosen_card) pairs from a finished round, replays
each of South's decisions through the Hard AI and reports whether the human
made the AI's preferred call. Educational only — never affects scoring.

Used optionally from gameflow's post-round flow when the player presses 'R'
on the round summary screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ai import AIPlayer, Difficulty
from .deck import Card
from .game import GameState, Seat


@dataclass(frozen=True)
class DecisionReport:
    trick_number: int
    chosen: Card
    suggested: Card
    matched: bool


def analyze_round(
    decisions: list[tuple[GameState, Card]], seat: Seat = Seat.SOUTH
) -> list[DecisionReport]:
    """Replay the given decisions through the Hard AI for `seat` and return
    a per-decision report.

    Each tuple is the (state-just-before-the-decision, card-actually-played).
    The function is pure; it doesn't mutate any inputs.
    """
    ai = AIPlayer(seat, Difficulty.HARD)
    reports: list[DecisionReport] = []
    for state, chosen in decisions:
        # Decide_card requires the state's turn to be the seat. Skip otherwise.
        if state.turn != seat:
            continue
        ai.update_memory(state)
        try:
            suggested = ai.decide_card(state)
        except Exception:  # noqa: BLE001
            continue
        trick_idx = len(state.completed_tricks) + 1
        reports.append(
            DecisionReport(
                trick_number=trick_idx,
                chosen=chosen,
                suggested=suggested,
                matched=chosen == suggested,
            )
        )
    return reports


def summarize(reports: list[DecisionReport]) -> str:
    """One-line summary suitable for the UI footer.

    Example: ``"Optimal: 6/8 (75%)"``.
    """
    if not reports:
        return "No decisions to analyze."
    matched = sum(1 for r in reports if r.matched)
    pct = int(round(100 * matched / len(reports)))
    return f"Optimal plays: {matched}/{len(reports)} ({pct}%)"
