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
    from belote.game import GameState

    print(f"Benchmarking BelAtro State Update ({num_jokers} Jokers) over {iterations} iterations...")

    jokers = [LeDiplomate() for _ in range(num_jokers)]
    acc = ScoreAccumulator()
    acc.attach_jokers(jokers)
    
    state = new_game()
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
        _ = acc.update_state(state, event)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    std = statistics.stdev(times) * 1000 if len(times) > 1 else 0
    print(f"  State Update Time: {avg:.3f}ms (±{std:.3f}ms)")
    return avg


def benchmark_scoring(iterations: int = 1000) -> float:
    from belote.scoring import score_round
    from belote.deck import Card, Rank
    from belote.game import TrickCard, Phase, replace
    
    print(f"Benchmarking score_round() over {iterations} iterations...")
    
    state = new_game()
    state = replace(
        state, 
        phase=Phase.SCORING, 
        trump=Suit.SPADES, 
        taker=Seat.SOUTH,
        completed_tricks=tuple([(TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),) * 4] * 8),
        last_trick_winner=Seat.SOUTH
    )
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = score_round(state)
        times.append(time.perf_counter() - start)
        
    avg = statistics.mean(times) * 1000
    print(f"  Scoring Time: {avg:.3f}ms")
    return avg


def benchmark_deal(iterations: int = 1000) -> float:
    from belote.game import start_round
    print(f"Benchmarking start_round() (deal) over {iterations} iterations...")
    
    state = new_game()
    rng = random.Random(42)
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = start_round(state, rng)
        times.append(time.perf_counter() - start)
        
    avg = statistics.mean(times) * 1000
    print(f"  Deal Time: {avg:.3f}ms")
    return avg


def benchmark_legal_cards(iterations: int = 1000) -> float:
    from belote.game import legal_cards, clear_legal_cards_cache, replace
    print(f"Benchmarking legal_cards() (cache cleared per call) over {iterations} iterations...")

    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, turn=Seat.SOUTH)

    times = []
    for _ in range(iterations):
        clear_legal_cards_cache()
        start = time.perf_counter()
        _ = legal_cards(state, Seat.SOUTH)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    print(f"  Legal Cards (cold) Time: {avg:.3f}ms")
    return avg


def benchmark_legal_cards_cached(iterations: int = 1000) -> float:
    """Measure the cache-hit path. Production gameplay reuses the cache across
    multiple AI rollouts and HUD redraws for the same `(state, seat)` pair —
    `benchmark_legal_cards` above invalidates every iteration and so reflects
    worst-case-only time.
    """
    from belote.game import legal_cards, clear_legal_cards_cache, replace
    print(f"Benchmarking legal_cards() (warm cache) over {iterations} iterations...")

    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, turn=Seat.SOUTH)
    clear_legal_cards_cache()
    legal_cards(state, Seat.SOUTH)  # warm the cache once

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = legal_cards(state, Seat.SOUTH)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    print(f"  Legal Cards (warm) Time: {avg:.3f}ms")
    return avg


def benchmark_trick_scoring(iterations: int = 1000) -> float:
    """Measure `trick_card_points` — called 8× per round from `game.py::play_card`
    (HUD running total) and again from `scoring.py::_calculate_base_points`
    (final round score). One of the hottest functions in a played round.
    """
    from belote.game import TrickCard, replace
    from belote.deck import Card, Rank
    from belote.scoring import trick_card_points

    print(f"Benchmarking trick_card_points() over {iterations} iterations...")

    state = new_game()
    state = replace(state, trump=Suit.SPADES, contract="normal", taker=Seat.SOUTH)
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.NINE)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.SEVEN)),
    )

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = trick_card_points(state, trick)
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    print(f"  Trick Scoring Time: {avg:.3f}ms")
    return avg


def benchmark_ai_legality_filter(iterations: int = 500) -> float:
    """Isolate the legal-move filter step inside `AIPlayer.decide_card`. The
    AI calls `legal_cards` once per decision; an unrepresentative cold-cache
    benchmark above would over-attribute AI time to legality checks.
    """
    from belote.game import legal_cards, replace
    print(f"Benchmarking AI legality filter over {iterations} iterations...")

    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH, turn=Seat.NORTH)

    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        legal = legal_cards(state, Seat.NORTH)
        # The filter step: callers usually check membership in a 6-8 card hand.
        _ = [c for c in state.hands[Seat.NORTH.value] if c in legal]
        times.append(time.perf_counter() - start)

    avg = statistics.mean(times) * 1000
    print(f"  Legality Filter Time: {avg:.3f}ms")
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
    print()
    benchmark_scoring()
    benchmark_deal()
    benchmark_legal_cards()
    benchmark_legal_cards_cached()
    benchmark_trick_scoring()
    benchmark_ai_legality_filter()
    print("========================================")



if __name__ == "__main__":
    run_benchmarks()
