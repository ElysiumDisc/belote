from __future__ import annotations

import sys

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    light_gray_fg,
    menu_art_fg,
    menu_border_fg,
    white_fg,
)
from ..game import GameState, Seat
from ..input import Key, KeyReader
from ..themes import THEMES, theme_manager
from .announce import toggle_mute
from .prompts import show_help
from .render import get_term_size


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


def _render_main_menu_art(sel: int, options: list[str], frame: int, term_h: int) -> list[str]:
    """Render the full main menu art with cards logo and chalice container."""
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

    # If terminal is too short, skip the logo art to fit the cup
    if term_h < 42:
        return final_cup

    return get_cards_art() + [""] + final_cup


def show_theme_selector(reader: KeyReader) -> None:
    """Submenu to cycle through themes with live preview."""
    themes_list = list(THEMES.keys())
    try:
        sel = themes_list.index(theme_manager._current_theme_name)
    except ValueError:
        sel = 0

    while True:
        term_w, term_h = get_term_size()
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
            case Key.QUIT | Key.ESC | Key.ENTER:
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
        term_w, term_h = get_term_size()

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
            case Key.QUIT | Key.ESC:
                return current_diffs
            case Key.HELP:
                show_help(reader)
            case Key.MUTE:
                toggle_mute()
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
                return current_diffs


def show_main_menu(
    reader: KeyReader, diffs_map: dict[Seat, str], target: int, speed: str
) -> tuple[str, dict[Seat, str], int, str]:
    """Display the main menu and return (choice, diffs_map, target, speed)."""
    curr_target = target
    curr_speed = speed
    curr_diffs = diffs_map

    sel = 0
    targs = [500, 1000, 1500, 2000]
    spds = ["slow", "normal", "fast", "instant"]
    frame = 0

    while True:
        # Determine display difficulty
        unique_diffs = set(curr_diffs.values())
        diff_display = next(iter(unique_diffs)).capitalize() if len(unique_diffs) == 1 else "Mixed"

        options_labels = [
            "BelAtro",
            "Start Game",
            f"AI:     < {diff_display} >",
            f"Target: < {curr_target} >",
            f"Speed:  < {curr_speed.capitalize()} >",
            f"Theme:  < {theme_manager.get_current().name} >",
            "Rules & History",
            "Statistics",
            "Quit",
        ]

        term_w, term_h = get_term_size()
        out = clear_screen() + hide_cursor()

        # Build the art containing the menu
        all_lines = _render_main_menu_art(sel, options_labels, frame, term_h)

        # Center the entire block vertically and horizontally
        v_pad = max(0, (term_h - len(all_lines) - 2) // 2)

        lines = [""] * v_pad
        for line in all_lines:
            lines.append(ansi_center(line, term_w))

        lines.append("")
        lines.append(
            ansi_center(
                f"{light_gray_fg()}↑/↓: Navigate  ←/→: Change Settings  Enter: Confirm/Config  Q: Quit{RESET}",
                term_w,
            )
        )

        sys.stdout.write(out + "\r\n".join(lines))
        sys.stdout.flush()

        event = reader.read_timeout(0.3)
        if event is None:
            frame += 1
            continue

        match event.key:
            case Key.QUIT:
                return "Quit", curr_diffs, curr_target, curr_speed
            case Key.HELP:
                show_help(reader)
            case Key.MUTE:
                toggle_mute()
            case Key.THEME:
                themes_list = list(THEMES.keys())
                curr_theme = theme_manager._current_theme_name
                new_idx = (themes_list.index(curr_theme) + 1) % len(themes_list)
                theme_manager.set_current(themes_list[new_idx])
            case Key.UP:
                sel = (sel - 1) % len(options_labels)
            case Key.DOWN:
                sel = (sel + 1) % len(options_labels)
            case Key.LEFT | Key.RIGHT:
                delta = 1 if event.key == Key.RIGHT else -1
                if sel == 2:
                    # Change all AI difficulties at once
                    diffs = ["easy", "medium", "hard"]
                    # If mixed, start from medium
                    base_diff = next(iter(unique_diffs)) if len(unique_diffs) == 1 else "medium"
                    new_idx = (diffs.index(base_diff) + delta) % len(diffs)
                    new_diff = diffs[new_idx]
                    for s in [Seat.EAST, Seat.NORTH, Seat.WEST]:
                        curr_diffs[s] = new_diff
                elif sel == 3:
                    curr_target = targs[(targs.index(curr_target) + delta) % len(targs)]
                elif sel == 4:
                    curr_speed = spds[(spds.index(curr_speed) + delta) % len(spds)]
                elif sel == 5:
                    # Cycle theme with left/right
                    themes_list = list(THEMES.keys())
                    curr_theme = theme_manager._current_theme_name
                    new_idx = (themes_list.index(curr_theme) + delta) % len(themes_list)
                    theme_manager.set_current(themes_list[new_idx])
            case Key.ENTER:
                choice = [
                    "BelAtro",
                    "Start Game",
                    "AI Config",
                    "Target Score",
                    "Speed",
                    "Theme",
                    "Rules & History",
                    "Statistics",
                    "Quit",
                ][sel]
                if choice == "AI Config":
                    curr_diffs = show_ai_config(reader, curr_diffs)
                    continue
                if choice == "Theme":
                    show_theme_selector(reader)
                    continue
                if choice in ("BelAtro", "Start Game", "Quit", "Rules & History", "Statistics"):
                    return choice, curr_diffs, curr_target, curr_speed
                # For settings, Enter can also toggle forward
                if sel == 3:
                    curr_target = targs[(targs.index(curr_target) + 1) % len(targs)]
                elif sel == 4:
                    curr_speed = spds[(spds.index(curr_speed) + 1) % len(spds)]
                elif sel == 5:
                    themes_list = list(THEMES.keys())
                    curr_theme = theme_manager._current_theme_name
                    new_idx = (themes_list.index(curr_theme) + 1) % len(themes_list)
                    theme_manager.set_current(themes_list[new_idx])


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
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()
