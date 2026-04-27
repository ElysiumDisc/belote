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
import time

from .ansi import (
    RESET, clear_screen, hide_cursor, show_cursor,
    alt_screen_on, alt_screen_off, BOLD, gold_fg, white_fg,
)
from .input import KeyReader
from .deck import Suit
from .game import (
    GameState, Phase, Seat, new_game, start_round,
    play_card, legal_cards, team_of, partner,
    TrickCard, replace,
)
from .bidding import bidding_turn, process_bid
from .scoring import score_round, apply_round_score
from .ai import AIPlayer, Difficulty
from .ui import (
    display, prompt_card, prompt_bid, announce, 
    show_final_screen, show_main_menu, animate_score_update,
    show_rules,
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
            try:
                self._reader.restore()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Belote – 4-player terminal card game")
    parser.add_argument("--target", type=int, default=1000, help="Target score to win (default: 1000)")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium",
                        help="AI difficulty (default: medium)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument(
        "--speed", choices=["slow", "normal", "fast", "instant"], default="normal",
        help="Game pace: slow (1.5s), normal (0.7s), fast (0.25s), instant (0s). Default: normal",
    )
    return parser.parse_args()


# AI delay and trick pause durations per speed setting.
# (ai_move_delay, trick_result_pause, round_result_pause)
_SPEED_TIMINGS: dict[str, tuple[float, float, float]] = {
    "slow":    (1.5, 2.0, 4.0),
    "normal":  (0.7, 1.2, 2.5),
    "fast":    (0.25, 0.4, 1.0),
    "instant": (0.0, 0.0, 0.5),
}


def create_ai_players(difficulty: Difficulty) -> dict[Seat, AIPlayer]:
    """Create AI players for non-South seats."""
    return {
        Seat.EAST: AIPlayer(Seat.EAST, difficulty),
        Seat.NORTH: AIPlayer(Seat.NORTH, difficulty),
        Seat.WEST: AIPlayer(Seat.WEST, difficulty),
    }


def run_bidding(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
                ai_delay: float) -> GameState | None:
    """Run the bidding phase. Returns None if user quits."""
    current = state
    while current.phase == Phase.BIDDING:
        bidder = bidding_turn(current)

        if bidder == Seat.SOUTH:
            display(current, None)
            bid = prompt_bid(current, reader)
            if bid == "QUIT":
                return None
        else:
            ai = ai_players[bidder]
            bid = ai.decide_bid(current)
            display(current, None)
            if bid:
                sys.stdout.write(f"\r\n  {bidder.name} takes it as {bid.symbol}!\r\n")
            else:
                sys.stdout.write(f"\r\n  {bidder.name} passes\r\n")
            sys.stdout.flush()
            
            # If someone takes, pause longer so user can see it
            if bid:
                time.sleep(ai_delay * 2 + 0.5)
            else:
                time.sleep(ai_delay)

        current = process_bid(current, bid)  # type: ignore[arg-type]

    return current


def run_play(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
             ai_delay: float, trick_pause: float) -> GameState | None:
    """Run the play phase (all 8 tricks). Returns None if user quits."""
    current = state

    while current.phase == Phase.PLAYING:
        player = current.turn

        if player == Seat.SOUTH:
            card = prompt_card(current, reader)
            if card is None:
                return None
        else:
            ai = ai_players[player]
            ai.update_memory(current)
            card = ai.decide_card(current)

        # 1. Show the card on the mat IMMEDIATELY
        display_state = replace(current, current_trick=current.current_trick + (TrickCard(player, card),))
        display(display_state, None)

        # 2. Handle AI message and short delay for cards 1, 2, 3
        if player != Seat.SOUTH:
            sys.stdout.write(f"\r\n  {player.name} plays {card}\r\n")
            sys.stdout.flush()
            if len(display_state.current_trick) < 4:
                time.sleep(ai_delay)

        # 3. If this completes a trick, pause longer and show announcements
        if len(display_state.current_trick) == 4:
            if len(current.completed_tricks) == 7: # This was the 8th trick
                from .game import trick_winner_seat, team_of
                winner = trick_winner_seat(display_state.current_trick, current.trump)
                if winner:
                    team = "NS" if team_of(winner) == 0 else "EW"
                    announce(f"Dix de Der (Team {team})", duration=trick_pause * 0.8)
                    display(display_state, None)
                
                # Check for Capot while cards are still visible
                taker_team = team_of(current.taker) if current.taker else None
                if taker_team is not None:
                    # Previous tricks + this one
                    all_tricks = list(current.completed_tricks) + [display_state.current_trick]
                    is_capot = all(
                        team_of(trick_winner_seat(t, current.trump)) == taker_team
                        for t in all_tricks
                    )
                    if is_capot:
                        announce("CAPOT!", duration=trick_pause * 1.2)
                        display(display_state, None)
            
            time.sleep(trick_pause)

        # 4. Transition to next state
        current = play_card(current, card)

        if current.announced:
            announce(current.announced, duration=max(0.5, trick_pause * 0.6))
            display(current, None)

    return current


def run_round(state: GameState, reader: KeyReader, ai_players: dict[Seat, AIPlayer],
              ai_delay: float, trick_pause: float, round_pause: float) -> GameState | None:
    """Run a complete round: deal, bid, play, score. Returns None if user quits."""
    rng = random.Random()
    current = start_round(state, rng)

    current = run_bidding(current, reader, ai_players, ai_delay)

    if current is None:
        return None

    if current.phase == Phase.DEAL:
        announce("All passed - Reshuffling!", duration=round_pause * 0.5)
        return current  # All passed, redeal

    res_play = run_play(current, reader, ai_players, ai_delay, trick_pause)
    if res_play is None:
        return None
    current = res_play

    if current.phase == Phase.SCORING:
        breakdown = score_round(current)

        display(current, None)
        sys.stdout.write(f"\r\n{'='*50}\r\n")
        sys.stdout.write(f"  Round Results:\r\n")
        taker_name = current.taker.name if current.taker else "?"
        team_label = 'NS' if team_of(current.taker) == 0 else 'EW'
        sys.stdout.write(f"  Taker: {taker_name} (Team {team_label})\r\n")
        for msg in breakdown.messages:
            sys.stdout.write(f"  {BOLD}{gold_fg()}{msg}{RESET}\r\n")
        ns_pts = breakdown.taker_total if breakdown.taker_team == 0 else breakdown.defender_total
        ew_pts = breakdown.defender_total if breakdown.taker_team == 0 else breakdown.taker_total
        sys.stdout.write(f"  Team NS: {ns_pts} points\r\n")
        sys.stdout.write(f"  Team EW: {ew_pts} points\r\n")
        sys.stdout.write(f"{'='*50}\r\n\r\n")
        sys.stdout.flush()
        time.sleep(round_pause)

        # Animate score update
        ns_old, ew_old = current.team_scores
        if breakdown.taker_team == 0:
            target_ns = ns_old + breakdown.taker_total
            target_ew = ew_old + breakdown.defender_total
        else:
            target_ns = ns_old + breakdown.defender_total
            target_ew = ew_old + breakdown.taker_total
        
        animate_score_update(current, target_ns, target_ew)

        current = apply_round_score(current, breakdown)

    return current


def main() -> None:
    args = parse_args()
    ai_delay, trick_pause, round_pause = _SPEED_TIMINGS[args.speed]

    # Setup terminal
    guard = TerminalGuard()

    def _sig_handler(_signum: int, _frame: object) -> None:
        guard.restore()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    atexit.register(guard.restore)

    rng = random.Random(args.seed)

    try:
        with KeyReader() as reader:
            guard.enter(reader)  # type: ignore[arg-type]

            target = args.target
            difficulty = Difficulty(args.difficulty)
            speed = args.speed

            while True:
                choice, diff_val, target, speed = show_main_menu(reader, difficulty.value, target, speed)
                difficulty = Difficulty(diff_val)
                
                if choice == "Quit":
                    break
                
                if choice == "Rules & History":
                    show_rules(reader)
                    continue
                
                if choice != "Start Game":
                    # Settings are now updated live in show_main_menu
                    continue

                # Start Game
                ai_delay, trick_pause, round_pause = _SPEED_TIMINGS[speed]
                sys.stdout.write(alt_screen_on() + clear_screen() + hide_cursor())
                sys.stdout.flush()

                # Create AI players
                ai_players = create_ai_players(difficulty)

                # Seed AI random for reproducibility
                if args.seed is not None:
                    for ai in ai_players.values():
                        ai._rng = random.Random(args.seed)

                # Initialize game
                state = new_game(target=target)

                # Main game loop
                while state.phase != Phase.GAME_OVER:
                    if state.phase == Phase.DEAL:
                        # Start a new round
                        pass  # run_round will call start_round

                    res_round = run_round(state, reader, ai_players, ai_delay, trick_pause, round_pause)
                    if res_round is None:
                        break
                    state = res_round

                    # Check for game over
                    if state.phase == Phase.GAME_OVER:
                        break

                    # Check if both teams reached target
                    ns, ew = state.team_scores
                    if ns >= target or ew >= target:
                        from .game import replace
                        state = replace(state, phase=Phase.GAME_OVER)

                if state.phase == Phase.GAME_OVER:
                    # Show final screen
                    show_final_screen(state)

                    # Wait for Enter/R/Q
                    sys.stdout.write("\n  [Enter/Q] Main Menu  [R] Rematch")
                    sys.stdout.flush()
                    rematch = False
                    while True:
                        ev = reader.read()
                        if ev.key == Key.CHAR and ev.char and ev.char.lower() == 'r':
                            rematch = True
                            break
                        if ev.key in (Key.ENTER, Key.QUIT):
                            break
                    
                    if rematch:
                        # Skip the menu and start again
                        sys.stdout.write(alt_screen_off())
                        sys.stdout.flush()
                        continue
                
                sys.stdout.write(alt_screen_off())
                sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        guard.restore()


if __name__ == "__main__":
    main()
