"""Headless end-to-end classic rounds through `gameflow.run_round` (the
shared round engine + ClassicRound policy), with every UI call stubbed."""

from __future__ import annotations

import itertools
import random

import pytest

from belote import a11y
from belote import gameflow as gf
from belote.ai import AIPlayer, Difficulty
from belote.game import GameState, Phase, Seat, legal_bids, legal_cards, new_game


@pytest.fixture
def headless(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    log: list[tuple[str, str]] = []

    def stub(name: str, ret: object = None):  # type: ignore[no-untyped-def]
        def f(*a: object, **k: object) -> object:
            log.append((name, str(a[0]) if a and isinstance(a[0], str) else ""))
            return ret

        return f

    for name in (
        "display",
        "patch_trick_card",
        "slide_card_to_table_hint",
        "pulse_winner_glow",
        "animate_score_update",
        "show_hand_preview",
        "announce",
        "belote_stinger",
        "achievement_toast",
    ):
        monkeypatch.setattr(gf, name, stub(name))
    monkeypatch.setattr(gf, "update_stats_round", stub("update_stats_round", []))
    monkeypatch.setattr(gf, "interruptible_sleep", stub("sleep", False))
    monkeypatch.setattr(gf, "show_round_summary", stub("summary", True))
    monkeypatch.setattr(a11y, "speak", stub("speak"))
    return log


def _ai(seed: int) -> dict[Seat, AIPlayer]:
    return {
        s: AIPlayer(s, Difficulty.MEDIUM, rng=random.Random(seed + s.value))
        for s in (Seat.EAST, Seat.NORTH, Seat.WEST)
    }


def _south(monkeypatch: pytest.MonkeyPatch, rng: random.Random, undo_rate: float) -> list[str]:
    asked: list[str] = []

    def prompt_bid(state: GameState, reader: object) -> object:
        asked.append("bid")
        return "UNDO" if rng.random() < undo_rate else rng.choice(legal_bids(state))

    def prompt_card(state: GameState, reader: object, **k: object) -> tuple[object, GameState]:
        asked.append("card")
        if state.completed_tricks and rng.random() < undo_rate:
            return "UNDO", state
        return rng.choice(legal_cards(state, Seat.SOUTH)), state

    def prompt_coinche(state: GameState, reader: object) -> bool:
        asked.append("coinche")
        return False

    monkeypatch.setattr(gf, "prompt_bid", prompt_bid)
    monkeypatch.setattr(gf, "prompt_card", prompt_card)
    monkeypatch.setattr(gf, "prompt_coinche", prompt_coinche)
    monkeypatch.setattr(gf, "prompt_surcoinche", lambda *a: False)
    return asked


@pytest.mark.parametrize("seed", range(6))
def test_classic_rounds_complete_and_score(
    headless: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    _south(monkeypatch, random.Random(seed), undo_rate=0.0)
    state = new_game()
    for rnd in range(3):
        res = gf.run_round(state, None, _ai(seed), 0, 0, 0, [], rng=random.Random(seed * 10 + rnd))  # type: ignore[arg-type]
        assert res is not None
        assert res.phase == Phase.DEAL  # ready for the next deal either way
        if len(res.score_history) == len(state.score_history):  # all passed
            assert ("announce", "All passed - Reshuffling!") in headless
        else:
            assert len(res.score_history) == len(state.score_history) + 1
            assert sum(res.team_scores) > sum(state.team_scores)
        state = res


def test_classic_undo_never_reprompts_coinche_mid_play(
    headless: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undo during play resumes the shared engine mid-round; pre-4.10.0 the
    classic driver re-ran the coinche flow every time it resumed."""
    asked = _south(monkeypatch, random.Random(1), undo_rate=0.2)
    for seed in range(12):
        asked.clear()
        res = gf.run_round(new_game(), None, _ai(seed), 0, 0, 0, [], rng=random.Random(seed))  # type: ignore[arg-type]
        assert res is not None
        # Every coinche prompt must come right after a bid (the contract
        # being locked), never after a card prompt (a resumed play phase).
        for prev, cur in itertools.pairwise(asked):
            if cur == "coinche":
                assert prev == "bid", asked


def test_classic_quit_returns_none(
    headless: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _south(monkeypatch, random.Random(0), undo_rate=0.0)
    monkeypatch.setattr(gf, "prompt_bid", lambda state, reader: "QUIT")
    monkeypatch.setattr(gf, "prompt_card", lambda state, reader, **k: (None, state))
    for seed in range(4):
        assert (
            gf.run_round(new_game(), None, _ai(seed), 0, 0, 0, [], rng=random.Random(seed)) is None
        )  # type: ignore[arg-type]
