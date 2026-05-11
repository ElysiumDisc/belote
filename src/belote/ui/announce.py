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
    clear_line,
    clear_screen,
    gold_fg,
    hide_cursor,
    move,
    white_fg,
)
from ..game import GameState
from ..input import KeyReader, interruptible_sleep
from ..stats import get_session_stats, load_stats
from .render import display_hud, get_term_size


def announce(message: str, duration: float = 2.0, reader: KeyReader | None = None) -> None:
    """Display a transient announcement banner.

    Painted with absolute cursor positioning + clear_line so it never triggers
    a scroll, even when the cursor is parked on the bottom row of the alt
    screen. Writing \\r\\n at the bottom row scrolls the alt-screen on Konsole
    and other strict emulators, which leaks the previous frame onto rows the
    next render's blank padding doesn't repaint.
    """
    term_w, term_h = get_term_size()
    banner = ansi_center(
        f"{banner_bg()}{banner_fg()}  {BOLD} {message} {RESET}", term_w
    )
    sys.stdout.write(move(max(1, term_h - 1), 1) + clear_line() + banner)
    sys.stdout.flush()
    if reader and duration > 0:
        interruptible_sleep(duration, reader)
    else:
        time.sleep(duration)


def show_stats(reader: KeyReader) -> None:
    """Display global game statistics."""
    stats = load_stats()
    session = get_session_stats()

    # Load BelAtro profile
    from ..belatro.progression.save import SaveManager

    profile = SaveManager().load_profile()
    b_stats = profile.stats

    while True:
        term_w, term_h = get_term_size()

        lines = []
        lines.append(f"{BOLD}{gold_fg()}GLOBAL STATISTICS{RESET}")
        lines.append("=" * 17)
        lines.append("")

        # ── BELOTE (Classic) ────────────────────────────────────────────────
        lines.append(f"{BOLD}{white_fg()}CLASSIC BELOTE{RESET}")
        lines.append("-" * 14)
        win_rate = (stats.games_won / stats.games_played * 100) if stats.games_played > 0 else 0
        lines.append(
            f"  Games Played: {stats.games_played:<6} Won: {stats.games_won:<6} ({win_rate:.1f}%)"
        )
        avg_pts = (stats.total_points_scored / stats.total_rounds) if stats.total_rounds > 0 else 0
        lines.append(f"  Total Rounds: {stats.total_rounds:<6} Avg Pts/Rd: {avg_pts:.1f}")
        worst = stats.worst_round_score if stats.total_rounds > 0 else 0
        lines.append(f"  Best Rd: {stats.best_round_score:<10} Worst Rd: {worst}")
        lines.append(f"  Capots: {stats.capots_achieved:<6} Max Streak: {stats.max_capot_streak}")
        lines.append("")

        # ── BELATRO (Roguelite) ──────────────────────────────────────────────
        lines.append(f"{BOLD}{gold_fg()}BELATRO EXPANSION{RESET}")
        lines.append("-" * 17)
        lines.append(f"  Runs Won (Ante 8): {b_stats.get('runs_won', 0)}")
        lines.append(f"  Total Capots:      {b_stats.get('total_capots', 0)}")
        lines.append(
            f"  Special Wins:      Sans Atout: {b_stats.get('sans_atout_wins', 0)}  "
            f"Tout Atout: {b_stats.get('tout_atout_wins', 0)}"
        )
        lines.append(f"  Unlocks:           {len(profile.unlocked_ids)} items found")
        lines.append("")

        # ── OTHER ──────────────────────────────────────────────────────────
        # Trump usage
        trump_list = sorted(stats.most_used_trump.items(), key=lambda x: x[1], reverse=True)
        trump_str = " ".join(f"{k}:{v}" for k, v in trump_list)
        lines.append(f"  Trump Usage: {trump_str}")

        # Difficulty breakdown
        lines.append(f"  {UNDERLINE}Win Rate by AI Level:{RESET}")
        for diff, dstats in stats.difficulty_stats.items():
            dp = dstats["played"]
            dw = dstats["won"]
            dwr = (dw / dp * 100) if dp > 0 else 0
            lines.append(f"    {diff.capitalize():<8}: {dw}/{dp} ({dwr:.1f}%)")

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
