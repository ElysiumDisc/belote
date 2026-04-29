from __future__ import annotations

import time
import random
import sys
import statistics
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from belote.game import GameState, Phase, Seat, new_game, start_round, play_card
from belote.deck import Card, Suit, Rank
from belote.ai import AIPlayer, Difficulty
from belote.ui.render import render

def benchmark_render(iterations: int = 100):
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

def benchmark_ai(difficulty: Difficulty, iterations: int = 50):
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

def run_benchmarks():
    print("=== Belote-CLI Performance Benchmark ===")
    benchmark_render()
    print()
    benchmark_ai(Difficulty.EASY)
    benchmark_ai(Difficulty.MEDIUM)
    benchmark_ai(Difficulty.HARD)
    print("========================================")

if __name__ == "__main__":
    run_benchmarks()
