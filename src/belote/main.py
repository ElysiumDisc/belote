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
from .ui.announce import achievement_toast
from .ui.settings_menu import show_settings


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
        default=None,
        help="Target score to win (default: the saved setting, else "
        f"{GLOBAL_CONFIG.TARGET_SCORE})",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        default=None,
        help="AI difficulty for every seat (default: the saved setting, else medium)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--speed",
        choices=list(GLOBAL_CONFIG.SPEED_TIMINGS.keys()),
        default=None,
        help="Game pace (default: the saved setting, else normal)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from .themes import theme_manager

    theme_manager.load_selection()

    # Saved settings, with any CLI flags overriding them for this session.
    from . import settings as settings_mod

    prefs = settings_mod.load()
    if args.difficulty is not None:
        prefs.ai = dict.fromkeys(settings_mod.AI_SEATS, args.difficulty)
    if args.target is not None:
        prefs.target = args.target
    if args.speed is not None:
        prefs.speed = args.speed
    settings_mod.apply(prefs)

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

    # Composition root: wire the BelAtro expansion into the core UI's
    # extension points (the core itself never imports BelAtro).
    from .belatro import integration as belatro_integration

    belatro_integration.install()

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

            modes = belatro_integration.menu_modes()

            while True:
                choice = show_main_menu(reader, [label for label, _ in modes])

                if choice == "Quit":
                    flush_stats()
                    break

                launch = dict(modes).get(choice)
                if launch is not None:
                    launch(reader)
                    continue

                if choice == "Settings":
                    show_settings(reader, prefs)
                    continue

                if choice == "Rules & History":
                    show_rules(reader)
                    continue

                if choice == "Statistics":
                    show_stats(reader)
                    continue

                if choice != "Start Game":
                    continue

                # Start Game — already in alt-screen, just clear.
                target = prefs.target
                diffs_map = {
                    Seat.EAST: prefs.ai["east"],
                    Seat.NORTH: prefs.ai["north"],
                    Seat.WEST: prefs.ai["west"],
                }
                ai_delay, trick_pause, round_pause = GLOBAL_CONFIG.SPEED_TIMINGS[prefs.speed]
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

                        unlocked = update_stats_game(
                            won=(ns >= target and ns > ew),
                            num_rounds=len(state.score_history),
                            difficulty=difficulty_str,
                        )
                        flush_stats()
                        for achievement in unlocked:
                            achievement_toast(achievement, reader)

                if state.phase == Phase.GAME_OVER:
                    # Show final screen. Raw mode is active (OPOST off), so
                    # line breaks must be "\r\n" — a bare "\n" staircases.
                    show_final_screen(state)

                    sys.stdout.write(f"\r\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                    sys.stdout.write(
                        f"\r\n  {white_fg()}[Enter/Q] Menu  [H] History{RESET} "
                    )
                    sys.stdout.flush()

                    while True:
                        ev = reader.read()
                        if ev.key == Key.HIST:
                            show_history(state, reader)
                            show_final_screen(state)
                            sys.stdout.write(f"\r\n  {BOLD}{gold_fg()}GAME OVER{RESET}")
                            sys.stdout.write(
                                f"\r\n  {white_fg()}[Enter/Q] Menu  [H] History{RESET} "
                            )
                            sys.stdout.flush()
                        elif ev.key in (Key.ENTER, Key.QUIT, Key.EOF):
                            break

                # Back to menu — stay in alt-screen, just clear before the menu
                # loop starts redrawing.
                sys.stdout.write(clear_screen())
                sys.stdout.flush()

    except (KeyboardInterrupt, FitAbortedError):
        # FitAbortedError: the player quit from an in-game resize prompt
        # (`require_minimum` inside render/announce paths), not just the
        # startup one above. Exit cleanly via the finally block instead of
        # dumping a traceback over a raw-mode terminal.
        pass
    finally:
        flush_stats()
        guard.restore()


if __name__ == "__main__":
    main()
