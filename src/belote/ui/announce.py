from __future__ import annotations

import sys
import time
from dataclasses import replace

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    UNDERLINE,
    ansi_center,
    banner_bg,
    banner_fg,
    clear_screen,
    gold_fg,
    hide_cursor,
)
from ..context import AUDIO
from ..game import GameState
from ..input import KeyReader, interruptible_sleep
from ..stats import get_session_stats, load_stats
from .render import display_hud, get_term_size


def is_muted() -> bool:
    return AUDIO.is_muted()


def toggle_mute() -> bool:
    return AUDIO.toggle_mute()


def announce(message: str, duration: float = 2.0, reader: KeyReader | None = None) -> None:
    """Display a transient announcement banner."""
    sys.stdout.write(f"\r\n{banner_bg()}{banner_fg()}  {BOLD} {message} {RESET}\r\n")
    sys.stdout.flush()
    if reader and duration > 0:
        interruptible_sleep(duration, reader)
    else:
        time.sleep(duration)


def play_sound(kind: str) -> None:
    """Enhanced terminal sounds using frequency tones (where supported) or bells."""
    if AUDIO.is_muted():
        return

    # Use XTerm OSC 777 or simple bells for now to keep it cross-terminal
    if kind == "trick":
        sys.stdout.write("\a")
    elif kind == "belote":
        sys.stdout.write("\a\a")
    elif kind == "declaration":
        sys.stdout.write("\a")
    elif kind == "chute":
        sys.stdout.write("\a\a\a")
    elif kind == "capot":
        # Arpeggio-like bell sequence
        for _ in range(3):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.1)
    sys.stdout.flush()


def show_stats(reader: KeyReader) -> None:
    """Display global game statistics."""
    stats = load_stats()
    session = get_session_stats()

    while True:
        term_w, term_h = get_term_size()

        lines = []
        lines.append(f"{BOLD}{gold_fg()}GLOBAL STATISTICS{RESET}")
        lines.append("=" * 17)
        lines.append("")

        # Win Rate section
        win_rate = (stats.games_won / stats.games_played * 100) if stats.games_played > 0 else 0
        lines.append(
            f"  Games Played: {stats.games_played:<6} Won: {stats.games_won:<6} ({win_rate:.1f}%)"
        )
        lines.append("")

        # Points section
        avg_pts = (stats.total_points_scored / stats.total_rounds) if stats.total_rounds > 0 else 0
        lines.append(f"  Total Rounds: {stats.total_rounds:<6} Avg Pts/Rd: {avg_pts:.1f}")
        worst = stats.worst_round_score if stats.total_rounds > 0 else 0
        lines.append(f"  Best Rd: {stats.best_round_score:<10} Worst Rd: {worst}")
        lines.append("")

        # Trump usage
        trump_list = sorted(stats.most_used_trump.items(), key=lambda x: x[1], reverse=True)
        trump_str = " ".join(f"{k}:{v}" for k, v in trump_list)
        lines.append(f"  Trump Usage: {trump_str}")
        lines.append("")

        # Difficulty breakdown
        lines.append(f"  {UNDERLINE}Win Rate by AI Level:{RESET}")
        for diff, dstats in stats.difficulty_stats.items():
            dp = dstats["played"]
            dw = dstats["won"]
            dwr = (dw / dp * 100) if dp > 0 else 0
            lines.append(f"    {diff.capitalize():<8}: {dw}/{dp} ({dwr:.1f}%)")

        lines.append("")
        lines.append(f"  Capots: {stats.capots_achieved:<6} Max Streak: {stats.max_capot_streak}")
        lines.append(f"  Longest Game: {stats.longest_game_rounds} rounds")

        # Session Panel
        lines.append("")
        lines.append(f"{banner_bg()}{banner_fg()}       THIS SESSION       {RESET}")
        lines.append(
            f"  Games: {session.games_played} ({session.games_won} won)  Rounds: {session.total_rounds}"
        )
        lines.append(f"  Points: {session.total_points}  Capots: {session.capots}")

        lines.append("")
        lines.append(f"{DIM}Press [Any Key] to Return{RESET}")

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()

        event = reader.read()
        if event:
            break


def animate_score_update(
    state: GameState, target_ns: int, target_ew: int, duration: float = 1.0
) -> None:
    """Animate the team scores rolling up to their new values."""
    start_ns, start_ew = state.team_scores
    steps = 20
    delay = duration / steps

    for i in range(1, steps + 1):
        curr_ns = start_ns + (target_ns - start_ns) * i // steps
        curr_ew = start_ew + (target_ew - start_ew) * i // steps

        temp_state = replace(state, team_scores=(curr_ns, curr_ew))
        display_hud(temp_state)
        time.sleep(delay)
