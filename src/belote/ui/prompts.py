from __future__ import annotations

import sys
from .render import display, get_term_size
from ..deck import Card, Suit
from ..game import (
    GameState,
    Phase,
    Seat,
    legal_cards,
    sort_south_hand,
)
from ..ansi import (
    RESET, BOLD, DIM, REVERSE,
    gold_fg, white_fg, red_fg, black_fg,
    ansi_center, clear_screen, hide_cursor,
    visible_len, light_gray_fg, green_fg,
)
from ..input import KeyReader, Key
from ..rules import RULES_CONTENT
from .announce import toggle_mute, is_muted # Need to implement these or import correctly

def prompt_card(state: GameState, reader: KeyReader) -> Card | str | None:
    """Interactive card selection with arrow keys. Returns None if QUIT is pressed."""
    hand  = state.hand_of(Seat.SOUTH)
    legal = legal_cards(state, Seat.SOUTH)

    if not hand:
        raise ValueError("No cards in hand")
    if not legal:
        return hand[0]

    # Start selection on the first legal card
    sel = next((i for i, c in enumerate(hand) if c in legal), 0)

    while True:
        display(state, sel)
        event = reader.read()

        match event.key:
            case Key.QUIT:
                return None
            case Key.LEFT | Key.UP:
                new = sel - 1
                while new >= 0 and hand[new] not in legal:
                    new -= 1
                if new >= 0:
                    sel = new
            case Key.RIGHT | Key.DOWN:
                new = sel + 1
                while new < len(hand) and hand[new] not in legal:
                    new += 1
                if new < len(hand):
                    sel = new
            case Key.ENTER:
                if hand[sel] in legal:
                    card = hand[sel]
                    if card in hand:
                        return card
                # Fallback: return nearest legal card
                for delta in range(1, len(hand)):
                    for d in (delta, -delta):
                        idx = sel + d
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            card = hand[idx]
                            if card in hand:
                                return card
            case Key.HELP:
                show_help(reader)
                continue
            case Key.SORT:
                selected_card = hand[sel]
                state = sort_south_hand(state)
                hand = state.hand_of(Seat.SOUTH)
                legal = legal_cards(state, Seat.SOUTH)
                # Re-find selection index
                sel = next((i for i, c in enumerate(hand) if c == selected_card), 0)
                continue
            case Key.MUTE:
                toggle_mute()
                continue
            case Key.CHAR:
                if event.char:
                    char = event.char.lower()
                    if char == 't':
                        show_history(state, reader)
                        continue
                    if char == 'z':
                        return "UNDO"
                    if char.isdigit():
                        idx = int(char) - 1
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            return hand[idx]
    return None

def prompt_bid(state: GameState, reader: KeyReader) -> Suit | str | None:
    """Interactive bid selection. Returns 'QUIT' if QUIT is pressed."""
    if state.bidding_round == 1:
        # Round 1: Take (up_card suit) or Pass
        options = [state.up_card.suit, None] # type: ignore[union-attr]
        labels  = [f"Take {state.up_card.suit.symbol}", "Pass"] # type: ignore[union-attr]
    else:
        # Round 2: Any suit except up_card suit, or Pass
        all_suits = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
        other_suits = [s for s in all_suits if s != state.up_card.suit] # type: ignore[union-attr]
        options = other_suits + [None]
        labels = [s.symbol for s in other_suits] + ["Pass"]
        
    sel = 0

    while True:
        display(state, None)
        term_w, _ = get_term_size()
        
        if state.bidding_round == 2:
            # Nice boxed UI for round 2
            inner_w = 40
            box_lines = [
                f"┌{'─' * inner_w}┐",
                f"│{f'ROUND {state.bidding_round} BID'.center(inner_w)}│",
                f"├{'─' * inner_w}┤",
                f"│{' ' * inner_w}│",
            ]
            
            # Options row
            opt_str = ""
            for i, opt in enumerate(options):
                lbl = labels[i]
                prefix = f"{BOLD}{gold_fg()}" if i == sel else ""
                suffix = RESET
                
                # Add color to suit symbols
                color = ""
                if isinstance(opt, Suit):
                    color = red_fg() if opt.is_red else black_fg()
                
                entry = f"{prefix}({i+1}) {color}{lbl}{RESET}{prefix}"
                if i == sel:
                    entry = f"{REVERSE} {entry} {RESET}"
                else:
                    entry = f" {entry} "
                opt_str += entry + "  "
            
            box_lines.append(f"│{ansi_center(opt_str.strip(), inner_w)}│")
            box_lines.append(f"│{' ' * inner_w}│")
            box_lines.append(f"└{'─' * inner_w}┘")
            
            for bl in box_lines:
                sys.stdout.write("\r\n" + ansi_center(bl, term_w))
            sys.stdout.write("\r\n")
        else:
            # Round 1 simple prompt
            parts = [
                f"{BOLD}{gold_fg()}({i+1}){lbl}{RESET}" if i == sel else f"({i+1}){lbl}"
                for i, lbl in enumerate(labels)
            ]
            prompt = f"{BOLD}{white_fg()}Round {state.bidding_round} Bid: {'  '.join(parts)}{RESET}"
            sys.stdout.write("\r\n" + ansi_center(prompt, term_w) + "\r\n")
            
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.QUIT:
                return "QUIT"
            case Key.LEFT | Key.UP:
                sel = (sel - 1) % len(options)
            case Key.RIGHT | Key.DOWN:
                sel = (sel + 1) % len(options)
            case Key.ENTER:
                return options[sel]
            case Key.HELP:
                show_help(reader)
                continue
            case Key.MUTE:
                toggle_mute()
                continue
            case Key.CHAR:
                if event.char:

                    char = event.char.lower()
                    if char == 't':
                        show_history(state, reader)
                        continue
                    if char == 'z':
                        return "UNDO"
                    if char == 'p':
                        return None
                    try:
                        idx = int(char) - 1
                        if 0 <= idx < len(options):
                            return options[idx]
                    except ValueError:
                        pass

def show_help(reader: KeyReader) -> None:
    """Display a quick keyboard shortcut reference."""
    term_w, term_h = get_term_size()
    sound_status = f"{red_fg()}OFF{RESET}" if is_muted() else f"{green_fg()}ON{RESET}"
    
    lines = [
        f"{BOLD}{gold_fg()}KEYBOARD SHORTCUTS{RESET}",
        "=" * 20,
        "",
        f"{white_fg()}General:{RESET}",
        "  [?] or [H]  Show this help screen",
        "  [Q]         Quit to menu / Exit",
        "  [M]         Toggle Sound Effects",
        f"              (Currently: {sound_status})",
        "  [Esc]       Cancel / Back",
        "",
        f"{white_fg()}Gameplay:{RESET}",
        "  [←↑→↓]      Move selection",
        "  [Enter]     Confirm selection",
        "  [1-8]       Quick card select",
        "  [O]         Sort hand by suit/rank",
        "  [Space]     Skip animations",
        "  [T]         View Game History",
        "  [Z]         Undo last move",
        "",
        f"{white_fg()}Bidding:{RESET}",
        "  [P]         Pass",
        "  [1-4]       Bid suit (S/H/D/C)",
        "",
        f"{white_fg()}Menus:{RESET}",
        "  [R]         Rematch (Game Over)",
        "  [T]         View Game History",
        "",
        f"{DIM}Press [Any Key] to Return{RESET}"
    ]

    out = clear_screen() + hide_cursor()
    rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
    sys.stdout.write("".join([out, rendered]))
    sys.stdout.flush()
    reader.read()

def show_rules(reader: KeyReader) -> None:
    """Display scrollable rules and history in EN/FR."""
    lang = "en"
    scroll = 0
    
    # Pre-render both languages
    cached_renders: dict[str, list[str]] = {}
    
    def get_render(l: str) -> list[str]:
        if l in cached_renders:
            return cached_renders[l]
        
        content = RULES_CONTENT[l]
        lines = []
        lines.append(f"{BOLD}{gold_fg()}{content['title']}{RESET}")
        lines.append("=" * visible_len(content['title']))
        lines.append("")
        
        for section in content['sections']:
            lines.append(f"{BOLD}{white_fg()}{section['header']}{RESET}")
            lines.append("-" * len(section['header']))
            # Wrap text manually
            words = section['text'].split()
            line = "  "
            for w in words:
                if len(line) + len(w) > 70:
                    lines.append(line)
                    line = "  " + w + " "
                else:
                    line += w + " "
            lines.append(line)
            lines.append("")
            
        lines.append(f"{DIM}Press [L] to Toggle Language ({l.upper()}) | [Q/Enter] Back{RESET}")
        cached_renders[l] = lines
        return lines

    while True:
        term_w, term_h = get_term_size()
        all_lines = get_render(lang)

        # Window the lines
        view_h = term_h - 4
        scroll = max(0, min(scroll, len(all_lines) - view_h))
        visible_lines = all_lines[scroll : scroll + view_h]
        
        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible_lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()
        
        event = reader.read()
        match event.key:
            case Key.QUIT | Key.ENTER | Key.ESC:
                return
            case Key.HELP:
                show_help(reader)
            case Key.MUTE:
                toggle_mute()
            case Key.UP:
                scroll = max(0, scroll - 1)
            case Key.DOWN:
                scroll = min(len(all_lines) - view_h, scroll + 1)
            case Key.CHAR:
                if event.char and event.char.lower() == 'l':
                    lang = "fr" if lang == "en" else "en"
                    scroll = 0

def show_history(state: GameState, reader: KeyReader) -> None:
    """Display a scrollable overlay of round-by-round scores."""
    scroll = 0
    
    while True:
        term_w, term_h = get_term_size()
        
        lines = []
        lines.append(f"{BOLD}{gold_fg()}GAME HISTORY{RESET}")
        lines.append("=" * 12)
        lines.append("")
        
        if not state.score_history:
            lines.append(f"{DIM}No rounds completed yet.{RESET}")
        else:
            # Table Header
            header = f"{'RD':<3} | {'TAKER':<5} | {'NS':^15} | {'EW':^15}"
            lines.append(f"{BOLD}{white_fg()}{header}{RESET}")
            lines.append("-" * len(header))
            
            for i, rs in enumerate(state.score_history):
                rd = i + 1
                taker = "NS" if rs.taker_team == 0 else "EW"
                
                # Format: "Card+Decl+Bel"
                ns_break = f"{rs.ns_card_pts}+{rs.ns_decl_pts}+{rs.ns_belote_pts}"
                ew_break = f"{rs.ew_card_pts}+{rs.ew_decl_pts}+{rs.ew_belote_pts}"
                
                ns_total = f"{BOLD}{rs.ns_total}{RESET}"
                ew_total = f"{BOLD}{rs.ew_total}{RESET}"
                
                row = f"{rd:<3} | {taker:<5} | {ns_total:>3} ({ns_break:<9}) | {ew_total:>3} ({ew_break:<9})"
                
                status = ""
                if rs.is_capot: status = f" {gold_fg()}CAPOT!{RESET}"
                elif rs.is_failed: status = f" {red_fg()}CHUTE!{RESET}"
                
                lines.append(row + status)

        lines.append("")
        lines.append(f"{DIM}Press [Any Key] to Return{RESET}")

        view_h = term_h - 4
        scroll = max(0, min(scroll, len(lines) - view_h))
        visible_lines = lines[scroll : scroll + view_h]
        
        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible_lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()
        
        event = reader.read()
        if event:
            return
