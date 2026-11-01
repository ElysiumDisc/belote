"""Profile the hot paths: render(), a classic round, a BelAtro round.

Prints the top functions by cumulative time for each target (cProfile), so
optimisation starts from data, not guesses (see DEVELOPMENT.md
"Performance"). For a sampling profile of the real game, use py-spy instead::

    py-spy record -o profile.svg -- python -m belote

Usage (from the repo root)::

    python scripts/hotspots.py                 # all targets, top 30
    python scripts/hotspots.py render --top 15
    python scripts/hotspots.py classic belatro --sort tottime
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import random
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _render_target() -> Callable[[], None]:
    from dataclasses import replace

    import belote.ui.render  # noqa: F401 — `belote.ui.render` the function shadows it
    from belote.context import TERMINAL
    from belote.deck import Suit
    from belote.game import Phase, Seat, new_game, start_round

    render_mod = sys.modules["belote.ui.render"]
    TERMINAL._size_cache = (120, 40)
    state = replace(
        start_round(new_game(), random.Random(42)),
        phase=Phase.PLAYING,
        trump=Suit.SPADES,
        taker=Seat.SOUTH,
    )

    def run() -> None:
        for i in range(2000):
            render_mod.render(state, selection=i % 8)

    return run


def _classic_target() -> Callable[[], None]:
    import fingerprint

    return lambda: fingerprint.classic_fingerprints(150)


def _belatro_target() -> Callable[[], None]:
    import fingerprint

    return lambda: fingerprint.belatro_fingerprints(200)


TARGETS: dict[str, tuple[str, Callable[[], Callable[[], None]]]] = {
    "render": ("2000 full-frame render() calls at 120x40", _render_target),
    "classic": ("150 seeded classic games (2 rounds, all-AI + random SOUTH)", _classic_target),
    "belatro": ("200 seeded BelAtro rounds (all bosses, random jokers)", _belatro_target),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("targets", nargs="*", choices=[*TARGETS, []], default=list(TARGETS))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--sort", default="cumulative", choices=["cumulative", "tottime", "ncalls"])
    args = ap.parse_args()

    for name in args.targets or TARGETS:
        label, build = TARGETS[name]
        fn = build()
        prof = cProfile.Profile()
        prof.enable()
        fn()
        prof.disable()
        buf = io.StringIO()
        stats = pstats.Stats(prof, stream=buf)
        stats.strip_dirs().sort_stats(args.sort).print_stats(args.top)
        print(f"=== {name}: {label} ===")
        print(buf.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
