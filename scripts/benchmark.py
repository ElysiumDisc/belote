from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from belote.ai import AIPlayer, Difficulty
from belote.deck import Suit
from belote.game import Phase, Seat, new_game, start_round
from belote.ui.render import render


def benchmark_render(iterations: int = 100) -> float:
    print(f"Benchmarking render() over {iterations} iterations...")

    # Setup a complex state (middle of play)
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)
    # Mock some state transitions to get into PLAYING phase
    from belote.game import replace

    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)

    times = []
    for i in range(iterations):
        # Vary the selection to avoid potential (though unlikely) pure-caching benefits in terminal output
        sel = i % 8
        start = time.perf_counter()
        _ = render(state, selection=sel)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    std = statistics.stdev(times) * 1000 if len(times) > 1 else 0
    print(f"  Render Time: {avg:.3f}ms (±{std:.3f}ms)")
    return avg


def benchmark_ai(difficulty: Difficulty, iterations: int = 50) -> float:
    print(f"Benchmarking AI ({difficulty.name}) decide_card() over {iterations} iterations...")

    ai = AIPlayer(Seat.NORTH, difficulty)

    # Setup a state
    state = new_game()
    rng = random.Random(42)
    state = start_round(state, rng)
    from belote.game import replace

    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = ai.decide_card(state)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    std = statistics.stdev(times) * 1000 if len(times) > 1 else 0
    print(f"  AI Decision Time: {avg:.3f}ms (±{std:.3f}ms)")
    return avg


def benchmark_belatro_bus(num_jokers: int = 5, iterations: int = 1000) -> float:
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import EventBus, TrickWonEvent
    from belote.belatro.items.jokers.contract import LeDiplomate
    from belote.deck import Card, Rank

    print(f"Benchmarking BelAtro Bus ({num_jokers} Jokers) over {iterations} iterations...")

    bus = EventBus()
    jokers = [LeDiplomate() for _ in range(num_jokers)]
    acc = ScoreAccumulator()
    acc.attach_jokers(jokers)
    bus.subscribe(acc.on_event)

    event = TrickWonEvent(
        winner=Seat.SOUTH,
        cards=tuple(Card(Suit.SPADES, r) for r in (Rank.JACK, Rank.NINE, Rank.ACE, Rank.TEN)),
        trick_number=1,
        is_last=False,
        card_points=40,
        trump=Suit.SPADES,
    )

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        bus.emit(event)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    std = statistics.stdev(times) * 1000 if len(times) > 1 else 0
    print(f"  Bus Emission Time: {avg:.3f}ms (±{std:.3f}ms)")
    return avg


def run_benchmarks() -> None:
    print("=== Belote-CLI Performance Benchmark ===")
    benchmark_render()
    print()
    benchmark_ai(Difficulty.EASY)
    benchmark_ai(Difficulty.MEDIUM)
    benchmark_ai(Difficulty.HARD)
    print()
    benchmark_belatro_bus()
    print("========================================")


if __name__ == "__main__":
    run_benchmarks()
