"""Seeded joker balance simulation for BelAtro.

For every registered joker, plays the same seeded rounds twice through the
real round driver (`belatro.engine.round_driver.drive_round`) — once with a
random baseline loadout, once with that loadout plus the joker — and reports
the paired difference:

* mean round score (chips × mult, as the blind is judged),
* win rate against the blind targets of the simulated ante,
* mean money the jokers paid out per round (economy jokers score $, not chips).

South is played by the Medium AI, so the rounds look like real play. Rounds
are simulated as short chains (one ante = 3 blinds by default) so jokers with
run-scoped counters (L'Horloger, Élan Tout-Atout) carry them between rounds,
like the run loop does.

Usage (from the repo root)::

    python scripts/balance.py                    # all jokers, 60 trials each
    python scripts/balance.py --trials 200 --ante 3
    python scripts/balance.py --jokers le_marechal,le_metronome

New 4.11.0 jokers are marked with ``*``. Deterministic for a given
``--seed`` (PYTHONHASHSEED is pinned like scripts/fingerprint.py).
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

NEW_IN_4_11 = frozenset(
    {
        "le_contrebandier",
        "le_marechal",
        "le_metronome",
        "la_commere",
        "l_horloger",
        "le_petit_poucet",
        "le_capitaine",
        "le_rempart",
        "le_joaillier",
        "le_maitre_d_atout",
        "la_remontee",
        "le_rentier",
    }
)


@dataclass
class Outcome:
    scores: list[int] = field(default_factory=list)
    wins: int = 0
    money: int = 0

    @property
    def rounds(self) -> int:
        return len(self.scores)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.scores) if self.scores else 0.0


def _ui(seed: int) -> Any:
    from belote.ai import AIPlayer, Difficulty
    from belote.belatro.engine.round_driver import RoundUICallbacks
    from belote.game import Seat

    class _AISouth(RoundUICallbacks):
        """South plays the Medium AI; every BelAtro prompt is declined."""

        def __init__(self) -> None:
            self.ai = AIPlayer(Seat.SOUTH, Difficulty.MEDIUM, rng=random.Random(seed))

        def prompt_bid(self, state: Any) -> Any:
            return self.ai.decide_bid(state)

        def prompt_card(self, state: Any) -> Any:
            return self.ai.decide_card(state), state

        def on_card_played(self, state: Any, seat: Any, card: Any) -> None:
            pass

        def on_trick_end(self, state: Any, winner: Any, points: int) -> None:
            pass

        def on_round_end(self, breakdown: object) -> None:
            pass

    return _AISouth()


def play_chain(joker_ids: list[str], seed: int, targets: list[int], money: int) -> Outcome:
    """Play `len(targets)` consecutive rounds with `joker_ids` equipped."""
    from belote.belatro.core.run_state import BelAtroRun
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import EventBus
    from belote.belatro.engine.round_driver import drive_round
    from belote.belatro.items.registry import registry
    from belote.belatro.main import BelAtroGame

    run = BelAtroRun(seed=seed)
    run.economy.money = money
    run.jokers = [registry.jokers[j]() for j in joker_ids]
    for joker in run.jokers:
        joker.on_purchase(run)  # corrupted jokers' run flags / trust costs
    out = Outcome()
    for i, target in enumerate(targets):
        acc = ScoreAccumulator(target_score=target)
        acc.attach_jokers(run.jokers)
        state = drive_round(
            bus=EventBus(),
            partner=run.partner,
            ui_callbacks=_ui(seed * 31 + i),
            acc=acc,
            seed=seed * 7919 + i,
            card_enhancements=BelAtroGame._round_flags(run),
        )
        total = acc.get_total(state)
        out.scores.append(total)
        out.wins += total >= target
        out.money += state._bonus_money
        BelAtroGame._harvest_round_state(run, state)
    return out


def simulate(
    joker_ids: list[str], pool: list[str], trials: int, seed: int, ante: int, money: int
) -> list[dict[str, Any]]:
    from belote.belatro.items.registry import registry
    from belote.belatro.run.ante import calculate_target

    targets = [calculate_target(ante, b) for b in range(3)]
    trial_rng = random.Random(seed)
    baselines = [trial_rng.sample(pool, trial_rng.randint(0, 3)) for _ in range(trials)]
    cache: dict[tuple[int, tuple[str, ...]], Outcome] = {}

    def run(i: int, loadout: list[str]) -> Outcome:
        key = (i, tuple(loadout))
        if key not in cache:
            cache[key] = play_chain(loadout, seed * 100_003 + i, targets, money)
        return cache[key]

    rows: list[dict[str, Any]] = []
    for j_id in joker_ids:
        without, with_ = Outcome(), Outcome()
        for i, base in enumerate(baselines):
            loadout = [b for b in base if b != j_id]
            a, b = run(i, loadout), run(i, [*loadout, j_id])
            without.scores += a.scores
            without.wins += a.wins
            without.money += a.money
            with_.scores += b.scores
            with_.wins += b.wins
            with_.money += b.money
        cls = registry.jokers[j_id]
        n = with_.rounds or 1
        rows.append(
            {
                "id": j_id,
                "name": cls.name,
                "rarity": cls.rarity.value,
                "cost": cls.cost,
                "new": j_id in NEW_IN_4_11,
                "mean_without": without.mean,
                "mean_with": with_.mean,
                "delta_pct": 100.0 * (with_.mean - without.mean) / max(without.mean, 1.0),
                "win_without": 100.0 * without.wins / n,
                "win_with": 100.0 * with_.wins / n,
                "money_delta": (with_.money - without.money) / n,
            }
        )
    rows.sort(key=lambda r: r["delta_pct"], reverse=True)
    return rows


def format_table(rows: list[dict[str, Any]]) -> str:
    head = (
        f"{'':1} {'joker':<22} {'rarity':<9} {'$':>2}  {'Δscore':>8}  "
        f"{'mean w/o → with':>17}  {'win% w/o → with':>16}  {'Δ$/rnd':>6}"
    )
    lines = [head, "─" * len(head)]
    for r in rows:
        lines.append(
            f"{'*' if r['new'] else ' '} {r['name'][:22]:<22} {r['rarity']:<9} {r['cost']:>2}  "
            f"{r['delta_pct']:>+7.1f}%  {r['mean_without']:>7.0f} → {r['mean_with']:<7.0f}  "
            f"{r['win_without']:>6.1f} → {r['win_with']:<6.1f}  {r['money_delta']:>+6.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--trials", type=int, default=60, help="seeded chains per joker")
    ap.add_argument("--ante", type=int, default=2, choices=range(1, 9), help="target ante")
    ap.add_argument("--money", type=int, default=20, help="wallet at chain start")
    ap.add_argument("--seed", type=int, default=411)
    ap.add_argument("--jokers", default="", help="comma-separated ids (default: all)")
    args = ap.parse_args()

    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()
    pool = sorted(registry.jokers)
    wanted = [j for j in args.jokers.split(",") if j] or pool
    unknown = [j for j in wanted if j not in registry.jokers]
    if unknown:
        ap.error(f"unknown joker ids: {', '.join(unknown)}")
    started = time.perf_counter()
    rows = simulate(wanted, pool, args.trials, args.seed, args.ante, args.money)
    print(
        f"{args.trials} trials × 3 rounds per joker (ante {args.ante} targets, "
        f"baseline 0-3 random jokers, seed {args.seed}) — "
        f"{time.perf_counter() - started:.1f}s"
    )
    print(format_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
