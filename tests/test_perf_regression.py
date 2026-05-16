"""Perf regression guard.

Times a handful of hot paths and compares the median against
``perf_baselines.json``. Fails only on severe regressions (>2.5x baseline)
to absorb cross-machine variance — warns on smaller drift via printed output.

Set ``BELOTE_SKIP_PERF=1`` in the environment to skip on slow CI runners.
Re-baseline deliberately by running ``scripts/benchmark.py`` and updating the
JSON sidecar with the new median values; record the date and host in the
``_comment`` field.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import time
from pathlib import Path

import pytest

from belote.deck import Card, Rank, Suit
from belote.game import (
    Phase,
    Seat,
    TrickCard,
    clear_legal_cards_cache,
    legal_cards,
    new_game,
    replace,
    start_round,
)
from belote.scoring import score_round, trick_card_points
from belote.ui.render import render

_BASELINES_PATH = Path(__file__).parent / "perf_baselines.json"
_HARD_THRESHOLD = 2.5  # fail if median > 2.5x baseline
_WARN_THRESHOLD = 1.2  # print warning if median > 1.2x baseline


def _skip_if_env() -> None:
    if os.environ.get("BELOTE_SKIP_PERF"):
        pytest.skip("BELOTE_SKIP_PERF set")


def _baselines() -> dict[str, float]:
    return {k: v for k, v in json.loads(_BASELINES_PATH.read_text()).items() if not k.startswith("_")}


def _median_ms(fn, iterations: int) -> float:
    times = []
    for _ in range(iterations):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return statistics.median(times) * 1000


def _check(name: str, observed_ms: float, baselines: dict[str, float]) -> None:
    baseline = baselines.get(name)
    assert baseline is not None, f"missing baseline for {name}"
    ratio = observed_ms / baseline if baseline > 0 else 0.0
    if ratio >= _WARN_THRESHOLD:
        print(
            f"\n[perf] {name}: observed {observed_ms:.3f}ms / baseline {baseline:.3f}ms ({ratio:.2f}x)"
        )
    assert ratio < _HARD_THRESHOLD, (
        f"{name} regressed {ratio:.2f}x baseline "
        f"(observed {observed_ms:.3f}ms, baseline {baseline:.3f}ms). "
        f"Re-baseline only if intentional."
    )


def test_render_perf_guard() -> None:
    _skip_if_env()
    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)
    counter = {"i": 0}

    def run() -> None:
        counter["i"] += 1
        render(state, selection=counter["i"] % 8)

    observed = _median_ms(run, iterations=30)
    _check("render_ms", observed, _baselines())


def test_legal_cards_cold_perf_guard() -> None:
    _skip_if_env()
    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, turn=Seat.SOUTH)

    def run() -> None:
        clear_legal_cards_cache()
        legal_cards(state, Seat.SOUTH)

    observed = _median_ms(run, iterations=200)
    _check("legal_cards_cold_ms", observed, _baselines())


def test_legal_cards_warm_perf_guard() -> None:
    _skip_if_env()
    state = new_game()
    state = start_round(state, random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, turn=Seat.SOUTH)
    clear_legal_cards_cache()
    legal_cards(state, Seat.SOUTH)  # warm

    def run() -> None:
        legal_cards(state, Seat.SOUTH)

    observed = _median_ms(run, iterations=500)
    _check("legal_cards_warm_ms", observed, _baselines())


def test_score_round_perf_guard() -> None:
    _skip_if_env()
    state = new_game()
    state = replace(
        state,
        phase=Phase.SCORING,
        trump=Suit.SPADES,
        taker=Seat.SOUTH,
        completed_tricks=tuple([(TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.ACE)),) * 4] * 8),
        last_trick_winner=Seat.SOUTH,
    )

    def run() -> None:
        score_round(state)

    observed = _median_ms(run, iterations=200)
    _check("score_round_ms", observed, _baselines())


def test_trick_card_points_perf_guard() -> None:
    _skip_if_env()
    state = new_game()
    state = replace(state, trump=Suit.SPADES, contract="normal", taker=Seat.SOUTH)
    trick = (
        TrickCard(Seat.SOUTH, Card(Suit.SPADES, Rank.JACK)),
        TrickCard(Seat.WEST, Card(Suit.SPADES, Rank.NINE)),
        TrickCard(Seat.NORTH, Card(Suit.HEARTS, Rank.ACE)),
        TrickCard(Seat.EAST, Card(Suit.SPADES, Rank.SEVEN)),
    )

    def run() -> None:
        trick_card_points(state, trick)

    observed = _median_ms(run, iterations=500)
    _check("trick_card_points_ms", observed, _baselines())
