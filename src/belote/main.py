"""Belote – 4-player terminal card game.

Usage:
    python -m belote.main [--target 1000] [--difficulty easy|medium|hard] [--seed 42]
"""

from __future__ import annotations

import argparse
import atexit
import random
import signal
import sys

from . import __version__
from .ansi import (
    BOLD,
    RESET,
    alt_screen_off,
    alt_screen_on,
    clear_screen,
    gold_fg,
    hide_cursor,
    show_cursor,
    white_fg,
)
from .config import GLOBAL_CONFIG
from .game import (
    GameState,
    Phase,
    Seat,
    new_game,
)
from .gameflow import create_ai_players, run_round
from .input import Key, KeyReader
from .stats import flush_stats, update_stats_game
from .ui import (
    show_final_screen,
    show_history,
    show_main_menu,
    show_rules,
    show_stats,
)


class TerminalGuard:
    """Ensure terminal is restored on exit."""

    def __init__(self) -> None:
        self._restored = False
        self._reader: KeyReader | None = None

    def enter(self, reader: KeyReader) -> None:
        self._reader = reader

    def restore(self, _signum: int = 0, _frame: object = None) -> None:
        if self._restored:
            return
        self._restored = True
        sys.stdout.write(alt_screen_off() + show_cursor() + RESET)
        sys.stdout.flush()
        if self._reader and not self._reader._restored:
            import contextlib

            with contextlib.suppress(Exception):
                self._reader.restore()


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
        if ivalue <= 0:
            raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
        return ivalue
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{value} is not an integer") from e


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Belote – 4-player terminal card game")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--target",
        type=positive_int,
        default=GLOBAL_CONFIG.TARGET_SCORE,
        help=f"Target score to win (default: {GLOBAL_CONFIG.TARGET_SCORE})",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        default="medium",
        help="AI difficulty (default: medium)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--speed",
        choices=list(GLOBAL_CONFIG.SPEED_TIMINGS.keys()),
        default="normal",
        help="Game pace. Default: normal",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from .themes import theme_manager

    theme_manager.load_selection()

    # Terminal-size enforcement now lives inside the alt-screen as a live
    # overlay (see require_minimum). Below the floor we paint a centered
    # "resize me" prompt that dismisses itself the instant the user resizes
    # past the floor — including mid-game shrinks.
    from .ui.fit_guard import FitAbortedError, require_minimum
    from .ui.layout import MIN_COLS, MIN_ROWS

    guard = TerminalGuard()

    def _sig_handler(_signum: int, _frame: object) -> None:
        guard.restore()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    atexit.register(guard.restore)

    try:
        with KeyReader() as reader:
            guard.enter(reader)

            # Enter alt-screen mode for the entire app session (menu + game).
            # Without this, every menu frame pollutes the terminal scrollback.
            sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
            sys.stdout.flush()

            try:
                require_minimum(reader, MIN_COLS, MIN_ROWS)
            except FitAbortedError:
                return

            target = args.target
            speed = args.speed
            diffs_map = {
                Seat.EAST: args.difficulty,
                Seat.NORTH: args.difficulty,
                Seat.WEST: args.difficulty,
            }

            rematch = False
            while True:
                if not rematch:
                    choice, diffs_map, target, speed = show_main_menu(
                        reader, diffs_map, target, speed
                    )

                    if choice == "Quit":
                        flush_stats()
                        break

                    if choice == "Rules & History":
                        show_rules(reader)
                        continue

                    if choice == "Statistics":
                        show_stats(reader)
                        continue

                    if choice == "BelAtro":
                        from .belatro.main import BelAtroGame

                        game = BelAtroGame()
                        game.start(reader)
                        continue

                    if choice != "Start Game":
                        continue

                # Start Game / Rematch — already in alt-screen, just clear.
                rematch = False
                ai_delay, trick_pause, round_pause = GLOBAL_CONFIG.SPEED_TIMINGS[speed]
                sys.stdout.write(clear_screen() + hide_cursor())
                sys.stdout.flush()

                # Create AI players
                ai_players = create_ai_players(diffs_map)

                # Seed AI random for reproducibility
                if args.seed is not None:
                    for i, ai in enumerate(ai_players.values()):
                        ai._rng = random.Random(args.seed + i)

                # Initialize game
                state = new_game(target=target)
                history_stack: list[GameState] = []
                game_rng = random.Random(args.seed) if args.seed is not None else random.Random()

                # Main game loop
                while state.phase != Phase.GAME_OVER:
                    # Run one complete round
                    res_round = run_round(
                        state,
                        reader,
                        ai_players,
                        ai_delay,
                        trick_pause,
                        round_pause,
                        history_stack,
                        game_rng,
                    )

                    if res_round is None:  # User quit mid-game
                        break
                    state = res_round

                    # `apply_round_score` (scoring.py) already set the correct
                    # phase: GAME_OVER when a team is ahead at/over target,
                    # DEAL on a tie at target so a tie-breaker round plays.
                    # Pre-3.4.0 this branch re-checked targets and forced
                    # GAME_OVER unconditionally, breaking the tie-breaker.
                    if state.phase == Phase.GAME_OVER:
                        ns, ew = state.team_scores
                        unique_diffs = set(diffs_map.values())
                        difficulty_str = (
                            next(iter(unique_diffs)) if len(unique_diffs) == 1 else "mixed"
                        )

                        update_stats_game(
                            won=(ns >= target and ns > ew),
                            num_rounds=len(state.score_history),
                            difficulty=difficulty_str,
                        )
                        flush_stats()

                if state.phase == Phase.GAME_OVER:
                    # Show final screen
                    show_final_screen(state)

                    # Wait for Enter/R/Q/T
                    sys.stdout.write(f"\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                    sys.stdout.write(
                        f"\n  {white_fg()}[Enter/Q] Menu  [R] Rematch  [H] History{RESET} "
                    )
                    sys.stdout.flush()

                    while True:
                        ev = reader.read()
                        if ev.key == Key.CHAR and ev.char and ev.char.lower() == "r":
                            rematch = True
                            break
                        if ev.key == Key.HIST:
                            show_history(state, reader)
                            show_final_screen(state)
                            sys.stdout.write(f"\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                            sys.stdout.write(
                                f"\n  {white_fg()}[Enter/Q] Menu  [R] Rematch  [H] History{RESET} "
                            )
                            sys.stdout.flush()
                        if ev.key in (Key.ENTER, Key.QUIT, Key.EOF):
                            rematch = False
                            break

                    if rematch:
                        continue

                # Back to menu — stay in alt-screen, just clear before the menu
                # loop starts redrawing.
                sys.stdout.write(clear_screen())
                sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        flush_stats()
        guard.restore()


if __name__ == "__main__":
    main()
