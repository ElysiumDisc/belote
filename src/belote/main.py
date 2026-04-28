from __future__ import annotations

"""Belote – 4-player terminal card game.

Usage:
    python -m belote.main [--target 1000] [--difficulty easy|medium|hard] [--seed 42]
"""

import argparse
import atexit
import random
import signal
import sys

from .ansi import (
    RESET, clear_screen, hide_cursor, show_cursor,
    alt_screen_on, alt_screen_off, BOLD, gold_fg, white_fg,
)
from .input import KeyReader, Key
from .game import (
    Phase, Seat, new_game, replace,
)
from .ui import (
    show_final_screen, show_main_menu,
    show_rules, show_history, show_stats,
)
from .stats import update_stats_game, flush_stats
from .gameflow import SPEED_TIMINGS, create_ai_players, run_round
from . import __version__


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
            try:
                self._reader.restore()
            except Exception:
                pass


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
        if ivalue <= 0:
            raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
        return ivalue
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not an integer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Belote – 4-player terminal card game")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--target", type=positive_int, default=1000, help="Target score to win (default: 1000)")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium",
                        help="AI difficulty (default: medium)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--speed", choices=["slow", "normal", "fast", "instant"], default="normal",
        help="Game pace: slow (1.5s), normal (0.7s), fast (0.25s), instant (0s). Default: normal",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Setup terminal
    guard = TerminalGuard()

    def _sig_handler(_signum: int, _frame: object) -> None:
        guard.restore()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    atexit.register(guard.restore)

    try:
        with KeyReader() as reader:
            guard.enter(reader)  # type: ignore[arg-type]

            target = args.target
            speed = args.speed
            mode = "Single Player"
            diffs_map = {Seat.EAST: args.difficulty, Seat.NORTH: args.difficulty, Seat.WEST: args.difficulty}

            rematch = False
            while True:
                if not rematch:
                    choice, diffs_map, target, speed, mode = show_main_menu(reader, diffs_map, target, speed, mode)
                    
                    if choice == "Quit":
                        flush_stats()
                        break
                    
                    if choice == "Rules & History":
                        show_rules(reader)
                        continue
                    
                    if choice == "Statistics":
                        show_stats(reader)
                        continue
                    
                    if choice != "Start Game":
                        continue

                # Start Game / Rematch
                rematch = False
                ai_delay, trick_pause, round_pause = SPEED_TIMINGS[speed]
                sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
                sys.stdout.flush()

                # Setup players
                human_seats = {Seat.SOUTH}
                if mode == "Hotseat (2P)":
                    human_seats.add(Seat.WEST)
                
                # Create AI players
                ai_players = create_ai_players(diffs_map, human_seats)

                # Seed AI random for reproducibility
                if args.seed is not None:
                    for ai in ai_players.values():
                        ai._rng = random.Random(args.seed)

                # Initialize game
                state = new_game(target=target)
                history_stack: list[GameState] = []

                # Main game loop
                while state.phase != Phase.GAME_OVER:
                    res_round = run_round(state, reader, ai_players, ai_delay, trick_pause, round_pause, history_stack, human_seats)
                    if res_round is None: # User quit mid-game
                        break
                    state = res_round

                    # Check for game over (after round end and score application)
                    ns, ew = state.team_scores
                    if ns >= target or ew >= target:
                        state = replace(state, phase=Phase.GAME_OVER)
                        
                        unique_diffs = set(diffs_map.values())
                        difficulty_str = next(iter(unique_diffs)) if len(unique_diffs) == 1 else "mixed"
                        
                        update_stats_game(
                            won=(ns >= target and ns >= ew),
                            num_rounds=len(state.score_history),
                            difficulty=difficulty_str
                        )
                        flush_stats()

                if state.phase == Phase.GAME_OVER:
                    # Show final screen
                    show_final_screen(state)

                    # Wait for Enter/R/Q/T
                    sys.stdout.write(f"\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                    sys.stdout.write(f"\n  {white_fg()}[Enter/Q] Menu  [R] Rematch  [T] History{RESET} ")
                    sys.stdout.flush()
                    
                    while True:
                        ev = reader.read()
                        if ev.key == Key.CHAR and ev.char:
                            if ev.char.lower() == 'r':
                                rematch = True
                                break
                            if ev.char.lower() == 't':
                                show_history(state, reader)
                                show_final_screen(state)
                                sys.stdout.write(f"\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                                sys.stdout.write(f"\n  {white_fg()}[Enter/Q] Menu  [R] Rematch  [T] History{RESET} ")
                                sys.stdout.flush()
                                continue
                        if ev.key in (Key.ENTER, Key.QUIT):
                            rematch = False
                            break
                    
                    if rematch:
                        continue
                
                # Back to menu
                sys.stdout.write(alt_screen_off())
                sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        flush_stats()
        guard.restore()


if __name__ == "__main__":
    main()
