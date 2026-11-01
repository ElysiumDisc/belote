from __future__ import annotations

import sys
from collections.abc import Sequence

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    ansi_center,
    clear_below,
    clear_screen,
    clear_to_eol,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    menu_art_fg,
    menu_border_fg,
    move,
    white_fg,
)
from ..game import GameState, Seat
from ..input import Key, KeyReader, key_label
from ..themes import THEMES, theme_manager
from .prompts import show_help
from .render import get_term_size, invalidate_diff


def get_cards_art() -> list[str]:
    """Return the croissant art with current theme colors.

    Each line is 25 Braille cells wide (including U+2800 blanks for indent),
    so callers can rely on uniform width without ASCII padding.
    """
    c = menu_art_fg()
    return [
        f"{c}⠀⠀⢠⣴⣶⣶⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⠀⠀⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⠀⢰⣿⣿⣿⣿⡿⠟⠁⣠⣴⣶⣦⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⠀⢸⣿⣿⠟⠉⣠⣴⣿⣿⣿⠟⠁⣠⣾⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⠀⠀⠉⣀⣴⣾⣿⣿⣿⠟⢁⣤⣾⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⢀⣤⣾⣿⣿⣿⡿⠛⢁⣴⣿⣿⣿⣿⣿⣿⣿⠟⠁⡀⠀⠀⠀⠀⠀{RESET}",
        f"{c}⢼⣿⣿⣿⡿⠋⣀⣴⣿⣿⣿⣿⣿⣿⣿⡿⠉⣠⣾⣿⡆⠀⠀⠀⠀{RESET}",
        f"{c}⠘⢿⡿⠋⣠⣾⣿⣿⣿⣿⣿⣿⣿⡿⠋⢀⣾⣿⣿⠟⢁⣀⠀⠀⠀{RESET}",
        f"{c}⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⠏⢀⣴⣿⣿⣿⠋⢠⣾⣿⣷⣦⡀{RESET}",
        f"{c}⠀⠀⢻⣿⣿⣿⣿⣿⣿⣿⠟⢁⣴⣿⣿⣿⡿⠁⣰⣿⣿⣿⣿⣿⣿{RESET}",
        f"{c}⠀⠀⠀⠹⢿⣿⣿⣿⡿⠋⣠⣾⣿⣿⣿⠟⢀⣼⣿⣿⣿⣿⣿⣿⡟{RESET}",
        f"{c}⠀⠀⠀⠀⠀⠉⠉⠉⠀⢾⣿⣿⣿⣿⠋⠀⠚⠛⠛⠛⠛⠛⠛⠁⠀{RESET}",
        f"{c}⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
    ]


CUP_TEMPLATE = [
    "                 {steam0}",
    "                 {steam1}",
    "                 {gold}___...(-------)-....___{reset}",
    "             {gold}.-''       )    (          ''-.{reset}",
    "       {gold}.-'``'|-._             )         _.-|{reset}",
    "      {gold}/  .--.|   `''---...........---''`   |{reset}",
    "     {gold}/  /    |{opt0}|{reset}",
    "     {gold}|  |    |{opt1}|{reset}",
    "     {gold}|  |    |{opt2}|{reset}",
    "     {gold}|  |    |{opt3}|{reset}",
    "     {gold}|  |    |{opt4}|{reset}",
    "     {gold}|  |    |{opt5}|{reset}",
    "     {gold}|  |    |{opt6}|{reset}",
    "      {gold}\\  \\   |{opt7}|{reset}",
    "       {gold}`\\ `\\ |{opt8}|{reset}",
    "         {gold}`\\ `|                             |{reset}",
    "         {gold}_/ /\\                             /{reset}",
    "        {gold}(__/  \\                           /{reset}",
    "     {gold}_..---''` \\                         /`''---.._{reset}",
    "  {gold}.-'           \\                       /          '-.{reset}",
    " {gold}:               `-.__             __.-'              :{reset}",
    " {gold}:                  ) ''---...---'' (                 :{reset}",
    "  {gold}'._               `''...___...--''`              _.'{reset}",
    " {gold}jgs \\''--..__                              __..--''/{reset}",
    "     {gold}'._     '''----.....______.....----'''     _.'{reset}",
    "        {gold}`''--..,,_____            _____,,..--''`{reset}",
    "                      {gold}`'''----'''`{reset}",
]

STEAMS = [
    ("      (      ", "       )     (", "      (      "),
    ("       )     ", "      (      )", "       )     "),
    ("      (      ", "       )     (", "      (      "),
    ("     (       ", "      )     (", "     (       "),
]


def _compact_menu(sel: int, options: list[str]) -> list[str]:
    """4.11.0: the menu for short terminals (e.g. 80×24), where the 27-row cup
    used to be clipped at the top: a one-line title and the entries."""
    title = f"{BOLD}{gold_fg()}♠ ♥   B E L O T E   ♦ ♣{RESET}"
    width = max(len(o) for o in options) + 4
    rows = [title, "", *(f"{menu_border_fg()}{'─' * width}{RESET}",)]
    for i, label in enumerate(options):
        text = f"> {label} <" if i == sel else f"  {label}  "
        cell = text.center(width)
        rows.append(f"{REVERSE}{cell}{RESET}" if i == sel else cell)
    rows.append(f"{menu_border_fg()}{'─' * width}{RESET}")
    return rows


def _render_main_menu_art(sel: int, options: list[str], frame: int, term_h: int) -> list[str]:
    """Render the full main menu art with cards logo and chalice container."""
    # Cup + the 2 footer rows + a margin row; below that, the compact menu.
    if term_h < len(CUP_TEMPLATE) + 3:
        return _compact_menu(sel, options)
    f = frame % 4
    st = STEAMS[f]

    # Process placeholders
    opts = {}
    assert len(options) <= 9, (
        f"Too many menu options ({len(options)}); add opt slots to CUP_TEMPLATE"
    )
    for i in range(9):
        label = options[i] if i < len(options) else ""
        text = f"{REVERSE}> {label} <{RESET}" if i == sel else f"  {label}  "
        opts[f"opt{i}"] = ansi_center(text, 29)

    final_cup = []
    for line in CUP_TEMPLATE:
        final_cup.append(
            line.format(
                steam0=f"{white_fg()}{st[0]}{RESET}",
                steam1=f"{white_fg()}{st[1]}{RESET}",
                gold=menu_border_fg(),
                reset=RESET,
                **opts,
            )
        )

    # Need: croissant + blank + cup + 2 footer rows + 1 top margin row.
    # Below that threshold, return the cup alone so it isn't pushed off-screen.
    cards = get_cards_art()
    croissant_min_h = len(cards) + 1 + len(CUP_TEMPLATE) + 2 + 1
    if term_h < croissant_min_h:
        return final_cup

    return cards + [""] + final_cup


def show_theme_selector(reader: KeyReader) -> None:
    """Submenu to cycle through themes with live preview."""
    themes_list = list(THEMES.keys())
    try:
        sel = themes_list.index(theme_manager.current_name)
    except ValueError:
        sel = 0

    while True:
        term_w, _ = get_term_size()
        theme_name = themes_list[sel]

        # Temporarily apply theme for preview
        theme_manager.set_current(theme_name)

        lines = []
        lines.append(f"{BOLD}{gold_fg()}SELECT THEME{RESET}")
        lines.append("=" * 16)
        lines.append("")

        for i, t_key in enumerate(themes_list):
            prefix = f"{BOLD}{gold_fg()}> " if i == sel else "  "
            display_name = THEMES[t_key].name
            lines.append(f"{prefix}{display_name}{RESET}")

        lines.append("")
        lines.append(f"{DIM}↑/↓: Navigate  Enter/ESC: Back{RESET}")

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.QUIT | Key.ESC | Key.ENTER | Key.EOF:
                invalidate_diff()
                return
            case Key.UP:
                sel = (sel - 1) % len(themes_list)
            case Key.DOWN:
                sel = (sel + 1) % len(themes_list)


def show_ai_config(reader: KeyReader, current_diffs: dict[Seat, str]) -> dict[Seat, str]:
    """Configure AI difficulty per seat."""
    sel = 0
    seats = [Seat.EAST, Seat.NORTH, Seat.WEST]
    diffs = ["easy", "medium", "hard"]

    while True:
        term_w, _ = get_term_size()

        lines = []
        lines.append(f"{BOLD}{gold_fg()}AI CONFIGURATION{RESET}")
        lines.append("=" * 16)
        lines.append("")

        for i, s in enumerate(seats):
            prefix = f"{BOLD}{gold_fg()}> " if i == sel else "  "
            lines.append(f"{prefix}{s.name}: < {current_diffs[s].capitalize()} >{RESET}")

        lines.append("")
        lines.append(f"{DIM}↑/↓: Navigate  ←/→: Change  Enter/ESC: Back{RESET}")

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.QUIT | Key.ESC | Key.EOF:
                invalidate_diff()
                return current_diffs
            case Key.HELP:
                show_help(reader)
            case Key.UP:
                sel = (sel - 1) % len(seats)
            case Key.DOWN:
                sel = (sel + 1) % len(seats)
            case Key.LEFT | Key.RIGHT:
                delta = 1 if event.key == Key.RIGHT else -1
                s = seats[sel]
                # Ensure we have a valid index
                try:
                    curr_idx = diffs.index(current_diffs[s])
                    new_idx = (curr_idx + delta) % len(diffs)
                    current_diffs[s] = diffs[new_idx]
                except ValueError:
                    current_diffs[s] = "medium"
            case Key.ENTER:
                invalidate_diff()
                return current_diffs


CORE_MENU_ENTRIES: tuple[str, ...] = (
    "Start Game",
    "Hot-seat & Spectate",
    "Settings",
    "Rules & History",
    "Statistics",
    "Quit",
)


def show_main_menu(reader: KeyReader, modes: Sequence[str] = ()) -> str:
    """Display the main menu and return the chosen entry's label.

    `modes` are extra game modes listed first (the entry point passes the
    expansion's modes, e.g. BelAtro); the core entries follow. AI / target /
    speed / theme live in the Settings screen.
    """
    options = [*modes, *CORE_MENU_ENTRIES]
    sel = 0
    frame = 0

    while True:
        term_w, term_h = get_term_size()
        # Repaint in place (home + per-row clear-to-EOL + erase-below) rather
        # than clear_screen(): this loop redraws every 300ms to animate the
        # steam, and a full-screen clear on each tick flickers on most
        # terminals. Every row is fully overwritten, so no debris survives.
        out = move(1, 1) + hide_cursor()
        all_lines = _render_main_menu_art(sel, options, frame, term_h)

        # Center the entire block vertically and horizontally
        v_pad = max(0, (term_h - len(all_lines) - 2) // 2)
        lines = [""] * v_pad
        for line in all_lines:
            lines.append(ansi_center(line, term_w))
        lines.append("")
        lines.append(
            ansi_center(
                f"{light_gray_fg()}↑/↓: Navigate  Enter: Select  {key_label('theme')}: Theme  "
                f"{key_label('help')}: Help  {key_label('quit')}: Quit{RESET}",
                term_w,
            )
        )

        sys.stdout.write(out + "\r\n".join(line + clear_to_eol() for line in lines) + clear_below())
        sys.stdout.flush()

        event = reader.read_timeout(0.3)
        if event is None:
            frame += 1
            continue

        match event.key:
            case Key.QUIT | Key.EOF:
                invalidate_diff()
                return "Quit"
            case Key.HELP:
                show_help(reader)
            case Key.THEME:
                theme_manager.cycle()
            case Key.UP:
                sel = (sel - 1) % len(options)
            case Key.DOWN:
                sel = (sel + 1) % len(options)
            case Key.ENTER:
                invalidate_diff()
                return options[sel]


def _step_target(targs: list[int], curr: int, delta: int) -> int:
    """Cycle the target score through the presets.

    `--target` accepts any positive int (e.g. 750), which isn't in `targs`;
    `targs.index` used to raise ValueError. A non-preset value snaps to the
    nearest preset in the pressed direction, wrapping like the presets do.
    """
    if curr in targs:
        return targs[(targs.index(curr) + delta) % len(targs)]
    if delta > 0:
        return next((t for t in targs if t > curr), targs[0])
    return next((t for t in reversed(targs) if t < curr), targs[-1])


def show_final_screen(state: GameState) -> None:
    """Display the game-over screen."""
    ns, ew = state.team_scores
    winner = "NS" if ns > ew else "EW"

    lines = [
        "",
        f"{BOLD}{gold_fg()}{'=' * 50}{RESET}",
        f"{BOLD}{gold_fg()}  GAME OVER{RESET}",
        f"{BOLD}{gold_fg()}{'=' * 50}{RESET}",
        "",
        f"  {white_fg()}Team NS: {ns} points{RESET}",
        f"  {white_fg()}Team EW: {ew} points{RESET}",
        "",
        f"  {BOLD}{gold_fg()}Winner: Team {winner}!{RESET}",
        "",
    ]

    sys.stdout.write(clear_screen())
    sys.stdout.write("\r\n".join(lines))
    sys.stdout.flush()
    invalidate_diff()
