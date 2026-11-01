"""Seeded whole-round fingerprints — the refactor regression guard.

Plays hundreds of deterministic rounds through the real engines with every UI
call stubbed, and hashes each round's final state + event trail:

* classic: ``gameflow.run_round`` with three Medium AIs and a seeded random
  SOUTH that sometimes undoes (``--classic`` rounds, default 450);
* BelAtro: ``round_driver.drive_round`` cycling every boss (plus no boss) with
  a seeded random joker loadout (``--belatro`` rounds, default 800).

Usage (from the repo root)::

    python scripts/fingerprint.py --save /tmp/before.json   # before a refactor
    python scripts/fingerprint.py --check /tmp/before.json  # after: must match

A pure refactor must be byte-identical. Exit status 1 lists the first rounds
that differ. Content additions (new jokers/bosses) legitimately change the
BelAtro pool, so re-baseline after adding content, not before.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_ADDR = re.compile(r" at 0x[0-9a-f]+")


def _digest(*parts: object) -> str:
    text = _ADDR.sub("", "\n".join(repr(p) for p in parts))
    return hashlib.sha256(text.encode()).hexdigest()


# ── classic ─────────────────────────────────────────────────────────────────


def classic_fingerprints(n: int) -> list[str]:
    from belote import a11y
    from belote import gameflow as gf
    from belote.ai import AIPlayer, Difficulty
    from belote.game import GameState, Seat, legal_bids, legal_cards, new_game

    log: list[str] = []

    def stub(name: str, ret: object = None) -> Any:
        def f(*a: object, **_k: object) -> object:
            log.append(name + (f":{a[0]}" if a and isinstance(a[0], str) else ""))
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
        setattr(gf, name, stub(name))
    gf.update_stats_round = stub("stats", [])  # type: ignore[assignment]
    gf.interruptible_sleep = stub("sleep", False)  # type: ignore[assignment]
    gf.show_round_summary = stub("summary", True)  # type: ignore[assignment]
    a11y.speak = stub("speak")  # type: ignore[assignment]

    out: list[str] = []
    for seed in range(n):
        log.clear()
        rng = random.Random(seed)
        undo_rate = (0.0, 0.05, 0.25)[seed % 3]

        def prompt_bid(
            state: GameState,
            _reader: object,
            rng: random.Random = rng,
            undo_rate: float = undo_rate,
        ) -> object:
            log.append("ask-bid")
            return "UNDO" if rng.random() < undo_rate else rng.choice(legal_bids(state))

        def prompt_card(
            state: GameState,
            _reader: object,
            rng: random.Random = rng,
            undo_rate: float = undo_rate,
            **_k: object,
        ) -> tuple[object, GameState]:
            log.append("ask-card")
            if state.completed_tricks and rng.random() < undo_rate:
                return "UNDO", state
            return rng.choice(legal_cards(state, Seat.SOUTH)), state

        def prompt_coinche(_state: GameState, _reader: object, rng: random.Random = rng) -> bool:
            return rng.random() < 0.15

        gf.prompt_bid = prompt_bid  # type: ignore[assignment]
        gf.prompt_card = prompt_card  # type: ignore[assignment]
        gf.prompt_coinche = prompt_coinche  # type: ignore[assignment]
        gf.prompt_surcoinche = lambda *_a, rng=rng: rng.random() < 0.3  # type: ignore[assignment]

        diff = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)[seed % 3]
        ais = {
            s: AIPlayer(s, diff, rng=random.Random(seed * 7 + s.value))
            for s in (Seat.EAST, Seat.NORTH, Seat.WEST)
        }
        state = new_game()
        history: list[GameState] = []
        for rnd in range(2):
            res = gf.run_round(
                state, None, ais, 0, 0, 0, history, rng=random.Random(seed * 10 + rnd)
            )  # type: ignore[arg-type]
            if res is None:
                break
            state = res
        out.append(_digest(state, log))
    return out


# ── BelAtro ─────────────────────────────────────────────────────────────────


def belatro_fingerprints(n: int) -> list[str]:
    from belote.belatro.core.scoring import ScoreAccumulator
    from belote.belatro.engine.event_bus import EventBus
    from belote.belatro.engine.round_driver import RoundUICallbacks, drive_round
    from belote.belatro.ghost_run import GhostRecorder
    from belote.belatro.items.registry import register_all_items, registry
    from belote.belatro.partner.partner_state import PartnerState
    from belote.belatro.run.boss import ALL_BOSS_MODIFIERS
    from belote.game import legal_bids, legal_cards

    register_all_items()
    joker_ids = sorted(registry.jokers)
    bosses: list[Any] = [None, *ALL_BOSS_MODIFIERS]

    class _UI(RoundUICallbacks):
        def __init__(self, rng: random.Random, log: list[str]) -> None:
            self.rng, self.log = rng, log

        def prompt_bid(self, state: Any) -> Any:
            return self.rng.choice(legal_bids(state))

        def prompt_card(self, state: Any) -> Any:
            return self.rng.choice(legal_cards(state, state.turn)), state

        def on_card_played(self, state: Any, seat: Any, card: Any) -> None:
            self.log.append(f"play:{seat.name}:{card}")

        def on_trick_end(self, state: Any, winner: Any, points: int) -> None:
            self.log.append(f"trick:{winner.name}:{points}")

        def on_round_end(self, breakdown: object) -> None:
            self.log.append(f"end:{breakdown!r}")

        def prompt_coinche(self, state: Any, taker: Any) -> bool:
            return self.rng.random() < 0.15

        def prompt_heist(self, state: Any) -> bool:
            return self.rng.random() < 0.5

        def prompt_surcoinche(self, state: Any, coincheur: Any) -> bool:
            return self.rng.random() < 0.3

    out: list[str] = []
    for seed in range(n):
        rng = random.Random(seed)
        log: list[str] = []
        k = rng.randint(0, 5)
        jokers = [registry.jokers[j]() for j in rng.sample(joker_ids, k)]
        acc = ScoreAccumulator(target_score=80 + 20 * (seed % 5))
        acc.attach_jokers(jokers)
        bus = EventBus()
        bus.subscribe(lambda e, log=log: log.append(type(e).__name__))
        boss_cls = bosses[seed % len(bosses)]
        recorder = GhostRecorder(seed=seed, deck_id="classique")
        try:
            state = drive_round(
                bus=bus,
                partner=PartnerState(),
                ui_callbacks=_UI(rng, log),
                acc=acc,
                boss=boss_cls() if boss_cls else None,
                seed=seed,
                recorder=recorder,
            )
            result: object = state
        except Exception as exc:  # a crash is part of the fingerprint too
            result = f"{type(exc).__name__}: {exc}"
        out.append(_digest(result, log, recorder.events, acc._log))
    return out


def main() -> int:
    # str/enum hashes are salted per process, so set iteration order (and any
    # decision that depends on it) varies between runs. Pin it.
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--classic", type=int, default=450)
    ap.add_argument("--belatro", type=int, default=800)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--save", type=Path)
    g.add_argument("--check", type=Path)
    args = ap.parse_args()

    data = {
        "classic": classic_fingerprints(args.classic),
        "belatro": belatro_fingerprints(args.belatro),
    }
    if args.save:
        args.save.write_text(json.dumps(data, indent=0))
        print(
            f"saved {len(data['classic'])} classic + {len(data['belatro'])} BelAtro → {args.save}"
        )
        return 0

    ref = json.loads(args.check.read_text())
    bad = 0
    for mode in ("classic", "belatro"):
        diffs = [i for i, (a, b) in enumerate(zip(ref[mode], data[mode], strict=False)) if a != b]
        if len(ref[mode]) != len(data[mode]):
            print(f"{mode}: round count differs ({len(ref[mode])} vs {len(data[mode])})")
            bad += 1
        if diffs:
            print(f"{mode}: {len(diffs)} rounds differ, first seeds: {diffs[:10]}")
            bad += 1
        else:
            print(f"{mode}: {len(data[mode])} rounds byte-identical")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
