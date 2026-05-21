from __future__ import annotations

import sys
import time

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
from ..game import GameState, team_of
from ..input import KeyEvent, KeyReader, interruptible_sleep
from ..scoring import ScoringBreakdown
from ..stats import get_session_stats, load_stats
from .render import display_hud, get_term_size, invalidate_diff


def belote_stinger(
    message: str, duration: float = 1.0, reader: KeyReader | None = None
) -> KeyEvent | None:
    """4.8.0 / C5: dramatic centered stinger for peak moments (Belote / Rebelote).

    A 4-row centered banner painted with absolute cursor positioning so it
    cannot scroll the alt-screen. Theme-aware via `banner_bg()` / `banner_fg()`
    / `gold_fg()` — looks great on the new Sunset Magma theme too. Skippable
    via any key press; returns the consumed `KeyEvent` if so. Always calls
    `invalidate_diff()` in `finally` per the 4.6.4 architectural rule.

    Replaces the modest one-line `announce(...)` call previously used for
    Belote / Rebelote so the moment actually lands. Other `announce(...)`
    call sites are unchanged.
    """
    term_w, term_h = get_term_size()
    # Box dimensions: a 4-row banner roughly 28 columns wide centered both
    # horizontally and vertically. On tight terminals (term_w < 32) we fall
    # back to the slim `announce()` styling rather than clipping the frame.
    box_w = 28
    if term_w < box_w + 4:
        return announce(message, duration=duration, reader=reader)

    box_top = max(2, (term_h - 4) // 2)
    title = f"  ✦  {message}  ✦  "
    title_padded = title.center(box_w - 2)
    top_border = "╔" + "═" * (box_w - 2) + "╗"
    blank_row = "║" + " " * (box_w - 2) + "║"
    title_row = "║" + title_padded + "║"
    bot_border = "╚" + "═" * (box_w - 2) + "╝"

    style = banner_bg() + banner_fg() + BOLD + gold_fg()
    parts: list[str] = []
    for i, line in enumerate((top_border, blank_row, title_row, bot_border)):
        parts.append(move(box_top + i, 1) + ansi_center(style + line + RESET, term_w))
    sys.stdout.write("".join(parts))
    sys.stdout.flush()

    try:
        if reader and duration > 0:
            return interruptible_sleep(duration, reader)
        if duration > 0:
            time.sleep(duration)
        return None
    finally:
        invalidate_diff()


def announce(
    message: str, duration: float = 2.0, reader: KeyReader | None = None
) -> KeyEvent | None:
    """Display a transient announcement banner.

    Painted with absolute cursor positioning + clear_line so it never triggers
    a scroll, even when the cursor is parked on the bottom row of the alt
    screen. Writing \\r\\n at the bottom row scrolls the alt-screen on Konsole
    and other strict emulators, which leaks the previous frame onto rows the
    next render's blank padding doesn't repaint.

    Returns the `KeyEvent` from `interruptible_sleep` if the user pressed a
    key to skip the pause (callers use this to propagate a `skip_anims` flag),
    otherwise `None`. Returning `None` for a non-interactive sleep (no reader
    or zero duration) preserves the pre-4.0.1 contract for callers that
    ignored the return.
    """
    term_w, term_h = get_term_size()
    banner = ansi_center(
        f"{banner_bg()}{banner_fg()}  {BOLD} {message} {RESET}", term_w
    )
    sys.stdout.write(move(max(1, term_h - 1), 1) + clear_line() + banner)
    sys.stdout.flush()
    # The banner is painted with absolute positioning, bypassing display()'s
    # diff cache. The next display() would diff against the pre-banner cached
    # frame and could skip repainting the banner row, leaving the message as a
    # ghost. Mirrors the finally pattern in animate_score_update (4.6.4).
    try:
        if reader and duration > 0:
            return interruptible_sleep(duration, reader)
        if duration > 0:
            time.sleep(duration)
        return None
    finally:
        invalidate_diff()


def show_round_summary(
    state: GameState,
    breakdown: ScoringBreakdown,
    reader: KeyReader,
    timeout: float = 0,
    replay_summary: str | None = None,
) -> bool:
    """End-of-round results modal. Replaces the pre-4.0.1 raw `\\r\\n`-dump
    in `gameflow.py:407-428` that was scrolling the alt-screen and corrupting
    the render-diff baseline.

    Painted with absolute cursor positioning so it cannot scroll. Returns
    `True` if the user pressed a key (signaling "skip remaining animations"),
    `False` if the `timeout` expired naturally. Always calls
    `invalidate_diff()` on exit so the next `display()` redraws the full
    game frame.
    """
    term_w, term_h = get_term_size()

    taker_name = state.taker.name if state.taker else "?"
    taker_team_label = (
        "NS" if state.taker is not None and team_of(state.taker) == 0 else "EW"
    )
    if breakdown.taker_team == 0:
        ns_pts = breakdown.taker_total
        ew_pts = breakdown.defender_total
    else:
        ns_pts = breakdown.defender_total
        ew_pts = breakdown.taker_total

    lines: list[str] = [
        f"{BOLD}{gold_fg()}══════ Round Results ══════{RESET}",
        "",
        f"{white_fg()}Taker:{RESET} {taker_name} (Team {taker_team_label})",
        "",
    ]
    for msg in breakdown.messages:
        lines.append(f"{BOLD}{gold_fg()}{msg}{RESET}")
    if breakdown.messages:
        lines.append("")
    lines.append(f"{white_fg()}Team NS:{RESET} {ns_pts} points")
    lines.append(f"{white_fg()}Team EW:{RESET} {ew_pts} points")
    if replay_summary:
        lines.append("")
        lines.append(f"{DIM}Replay: {replay_summary}{RESET}")
    lines.append("")
    if timeout > 0:
        footer = f"{DIM}[Any Key] continue  ({timeout:.1f}s){RESET}"
    else:
        footer = f"{DIM}[Any Key] continue{RESET}"
    lines.append(footer)

    start_row = max(1, (term_h - len(lines)) // 2)
    parts: list[str] = [clear_screen(), hide_cursor()]
    for i, line in enumerate(lines):
        parts.append(move(start_row + i, 1) + ansi_center(line, term_w))
    sys.stdout.write("".join(parts))
    sys.stdout.flush()

    event = reader.read_timeout(timeout) if timeout > 0 else reader.read()
    invalidate_diff()
    return event is not None


def show_stats(reader: KeyReader) -> None:
    """Display global game statistics."""
    stats = load_stats()
    session = get_session_stats()

    # Load BelAtro profile
    from ..belatro.progression.save import SaveManager

    profile = SaveManager().load_profile()
    b_stats = profile.stats

    # 4.1.1: hoist the line-list build outside the read loop. The stats numbers
    # are immutable for the lifetime of the modal — pre-4.1.1 every keystroke
    # rebuilt the full list AND re-walked the difficulty / trump dicts AND
    # re-formatted every f-string. Same cache pattern as _build_history_lines.
    lines: list[str] = []
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
    lines.append(f"  Discovered:        {len(profile.discovered_items)} items seen")
    lines.append(f"  Unlocked:          {len(profile.unlocked_ids)} items earned")
    lines.append("")

    # ── OTHER ──────────────────────────────────────────────────────────
    trump_list = sorted(stats.most_used_trump.items(), key=lambda x: x[1], reverse=True)
    trump_str = " ".join(f"{k}:{v}" for k, v in trump_list)
    lines.append(f"  Trump Usage: {trump_str}")

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

    # Cache the centered rendering per terminal width so a SIGWINCH mid-modal
    # rebuilds the frame, but repeated reads at the same width reuse it.
    last_w = -1
    rendered = ""
    try:
        while True:
            term_w, _ = get_term_size()
            if term_w != last_w:
                rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
                last_w = term_w
            out = clear_screen() + hide_cursor()
            sys.stdout.write("".join([out, rendered]))
            sys.stdout.flush()

            event = reader.read()
            if event:
                break
    finally:
        # 4.1.1: paint a stats screen → must invalidate the diff baseline so
        # the next display() emits a full frame. Same architectural rule as
        # fit_guard / BelAtro overlays.
        invalidate_diff()


def animate_score_update(
    state: GameState, target_ns: int, target_ew: int, duration: float = 1.0
) -> None:
    """Animate the team scores rolling up to their new values."""
    start_ns, start_ew = state.team_scores
    steps = 20
    delay = duration / steps

    try:
        for i in range(1, steps + 1):
            curr_ns = start_ns + (target_ns - start_ns) * i // steps
            curr_ew = start_ew + (target_ew - start_ew) * i // steps

            # 4.6.5: pass the intermediate scores as an override instead of
            # `replace(state, team_scores=...)`. Frozen GameState has ~50
            # fields; `replace` allocated a fresh one per frame × 20 frames.
            display_hud(state, team_scores_override=(curr_ns, curr_ew))
            time.sleep(delay)
    finally:
        # 4.6.4: display_hud writes row 1 directly to stdout, bypassing the
        # render-diff cache. Without this invalidation, a subsequent
        # display() with a row 1 that happens to match the cached pre-
        # animation row 1 would skip emitting it, leaving the last
        # animation frame painted on screen. Matches the same architectural
        # rule already applied by show_help / show_history / show_rules /
        # show_card_detail / show_stats.
        invalidate_diff()
