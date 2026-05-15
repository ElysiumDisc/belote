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
    from belote.belatro.engine.event_bus import TrickWonEvent
    from belote.belatro.items.jokers.contract import LeDiplomate
    from belote.deck import Card, Rank

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
    from belote.deck import Card, Rank
    from belote.game import Phase, TrickCard, replace
    from belote.scoring import score_round

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
    from belote.game import clear_legal_cards_cache, legal_cards, replace
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
    from belote.game import clear_legal_cards_cache, legal_cards, replace
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
    from belote.deck import Card, Rank
    from belote.game import TrickCard, replace
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


def benchmark_belatro_round(rounds: int = 30, seed: int = 42) -> float:
    """End-to-end BelAtro round throughput under a deterministic seed.

    Drives a full round (bid → 8 tricks → score) headlessly via the same
    round_driver path the game uses, with AI on every seat. The seed is
    threaded into drive_round so the per-round work is reproducible — a
    regression sentinel, not a wall-clock target.
    """
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import EventBus
    from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
    from belote.belatro.partner.partner_state import PartnerState
    from belote.deck import Card
    from belote.game import GameState, legal_cards

    class _HeadlessUI(RoundUICallbacks):
        def prompt_bid(self, state: GameState) -> Suit | None:
            return None  # pass; AI seats may take

        def prompt_card(self, state: GameState) -> tuple[Card, GameState]:
            return legal_cards(state, Seat.SOUTH)[0], state

        def on_card_played(self, state: GameState, seat: Seat, card: Card) -> None:
            pass

        def on_trick_end(self, state: GameState, winner: Seat, points: int) -> None:
            pass

        def on_round_end(self, breakdown: object) -> None:
            pass

    print(f"Benchmarking drive_round() E2E over {rounds} rounds (seed={seed})...")

    times = []
    for i in range(rounds):
        bus = EventBus()
        partner = PartnerState()
        acc = ScoreAccumulator()
        start = time.perf_counter()
        drive_round(bus=bus, partner=partner, ui_callbacks=_HeadlessUI(), acc=acc, seed=seed + i)
        times.append(time.perf_counter() - start)

    mean = statistics.mean(times) * 1000
    p95 = sorted(times)[int(len(times) * 0.95) - 1] * 1000 if len(times) > 1 else mean
    rps = 1.0 / statistics.mean(times) if times else 0.0
    print(f"  E2E Round Time: mean {mean:.2f}ms, p95 {p95:.2f}ms ({rps:.1f} rounds/sec)")
    return mean


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
    print()
    benchmark_belatro_round()
    print("========================================")


def run_smoke() -> None:
    """Tiny smoke pass: every benchmark runs once at minimum iteration count.
    Used by the test suite to keep the script from rotting.
    """
    benchmark_render(iterations=2)
    benchmark_ai(Difficulty.EASY, iterations=2)
    benchmark_belatro_bus(iterations=2)
    benchmark_scoring(iterations=2)
    benchmark_deal(iterations=2)
    benchmark_legal_cards(iterations=2)
    benchmark_legal_cards_cached(iterations=2)
    benchmark_trick_scoring(iterations=2)
    benchmark_ai_legality_filter(iterations=2)
    benchmark_belatro_round(rounds=2)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        run_smoke()
    else:
        run_benchmarks()
