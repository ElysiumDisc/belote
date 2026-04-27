from __future__ import annotations

import shutil
import sys
import time

from .deck import Card, Rank, Suit, card_points
from .game import (
    GameState,
    Phase,
    Seat,
    TrickCard,
    legal_cards,
    team_of,
    partner,
    trick_winner_seat,
    replace,
)
from .ansi import (
    RESET, BOLD, DIM, REVERSE, UNDERLINE,
    fg, clear_screen, hide_cursor, show_cursor,
    felt_bg, red_fg, black_fg, card_face_bg, card_back_bg,
    highlight_bg, gold_fg, white_fg, light_gray_fg, green_fg,
    banner_bg, banner_fg, visible_len, ansi_center, ansi_ljust,
    face_card_bg,
)
from .input import KeyReader, KeyEvent, Key
from .rules import RULES_CONTENT


# Card display dimensions — optimized for "Supreme Quality" 9x7 layout.
CARD_W = 9
CARD_H = 7
CARD_GAP = 1

# Fixed visible width for the WEST and EAST side columns in the middle section.
SIDE_COL_W = 22


def _card_symbol(card: Card) -> str:
    return f"{card.rank.value}{card.suit.symbol}"


def _card_face(card: Card, selected: bool = False, legal: bool = True) -> list[str]:
    """Render a card as CARD_H lines of width CARD_W with Art Nouveau styling."""
    rank_str = card.rank.value
    suit_sym = card.suit.symbol
    
    # Top-left and bottom-right rank displays
    tl_rank = rank_str.ljust(2)
    br_rank = rank_str.rjust(2)

    is_face = card.rank in (Rank.JACK, Rank.QUEEN, Rank.KING)
    
    color = red_fg() if card.suit.is_red else black_fg()
    
    if selected:
        bg_code = highlight_bg()
    elif is_face:
        bg_code = face_card_bg()
    else:
        bg_code = card_face_bg()

    prefix = "" if legal else DIM
    inner_w = CARD_W - 2
    
    # Ornate Art Nouveau-inspired elements
    art_top = " " * inner_w
    art_mid = " " * inner_w
    art_bot = " " * inner_w

    if card.rank == Rank.JACK:
        art_top = "  ▄▆▄  "
        art_mid = f"  {suit_sym}V{suit_sym}  "
        art_bot = "  ▀▆▀  "
    elif card.rank == Rank.QUEEN:
        art_top = "  ╭▼╮  "
        art_mid = f"  {suit_sym}Q{suit_sym}  "
        art_bot = "  ╰─╯  "
    elif card.rank == Rank.KING:
        art_top = "  ╔█╗  "
        art_mid = f"  {suit_sym}K{suit_sym}  "
        art_bot = "  ╚═╝  "
    elif card.rank == Rank.ACE:
        art_top = "   ▲   "
        art_mid = f"  {suit_sym}A{suit_sym}  "
        art_bot = "   ▼   "
    else:
        # Pips for numbered cards - simplified but elegant
        art_mid = f"   {suit_sym}   "

    # Use ornate border characters
    return [
        f"{prefix}{bg_code}{color}╔{'═' * inner_w}╗{RESET}",
        f"{prefix}{bg_code}{color}║{tl_rank}{' ' * (inner_w-2)}║{RESET}",
        f"{prefix}{bg_code}{color}║{art_top}║{RESET}",
        f"{prefix}{bg_code}{color}║{art_mid}║{RESET}",
        f"{prefix}{bg_code}{color}║{art_bot}║{RESET}",
        f"{prefix}{bg_code}{color}║{' ' * (inner_w-2)}{br_rank}║{RESET}",
        f"{prefix}{bg_code}{color}╚{'═' * inner_w}╝{RESET}",
    ]


def _card_back() -> list[str]:
    """Render a face-down card with an ornate pattern."""
    inner_w = CARD_W - 2
    # Decorative lattice pattern for the back
    pattern = [
        " ░▒▓▒░ ",
        " ░▒▓▒░ ",
        " ░▒▓▒░ ",
        " ░▒▓▒░ ",
        " ░▒▓▒░ ",
    ]
    
    res = [f"{card_back_bg()}╔{'═' * inner_w}╗{RESET}"]
    for line in pattern:
        res.append(f"{card_back_bg()}║{line}║{RESET}")
    res.append(f"{card_back_bg()}╚{'═' * inner_w}╝{RESET}")
    return res


def _card_back_small() -> str:
    """Single-line face-down card for opponent hand display."""
    return f"{card_back_bg()}▓▓{RESET}"


def _felt_blank(width: int) -> str:
    return felt_bg() + " " * width + RESET


def _felt_pad(content: str, width: int) -> str:
    """Center content on a green felt background of `width` visible chars."""
    vlen = visible_len(content)
    total_pad = max(0, width - vlen)
    lpad = total_pad // 2
    rpad = total_pad - lpad
    return felt_bg() + " " * lpad + RESET + content + felt_bg() + " " * rpad + RESET


def _felt_placeholder() -> list[str]:
    """Card-sized dashed outline on the felt — shown for an empty trick slot."""
    inner_w = CARD_W - 2
    dim = fg(35, 130, 70)
    top    = felt_bg() + dim + "┌" + "─" * inner_w + "┐" + RESET
    mid    = felt_bg() + dim + "│" + " " * inner_w + "│" + RESET
    bottom = felt_bg() + dim + "└" + "─" * inner_w + "┘" + RESET
    return [top] + [mid] * (CARD_H - 2) + [bottom]


def _render_trick_mat(seat_map: dict[Seat, Card], center_w: int) -> list[str]:
    """21-row green felt mat with full card graphics at compass positions."""
    def slot(seat: Seat) -> list[str]:
        return _card_face(seat_map[seat]) if seat in seat_map else _felt_placeholder()

    n_card = slot(Seat.NORTH)
    w_card = slot(Seat.WEST)
    e_card = slot(Seat.EAST)
    s_card = slot(Seat.SOUTH)

    # Horizontal anchors: West centred at ¼, East centred at ¾ of center_w
    w_start = max(0, center_w // 4 - CARD_W // 2)
    e_start = max(0, 3 * center_w // 4 - CARD_W // 2)
    mid_gap = max(0, e_start - w_start - CARD_W)
    r_pad   = max(0, center_w - e_start - CARD_W)

    n_label = _felt_pad(f"{light_gray_fg()}N{RESET}", center_w)
    s_label = _felt_pad(f"{light_gray_fg()}S{RESET}", center_w)

    rows: list[str] = []

    rows.append(_felt_blank(center_w))                       # top padding
    rows.append(n_label)                                     # N label
    for line in n_card:                                      # North card (7 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(_felt_blank(center_w))                       # gap
    for i in range(CARD_H):                                  # West + East (7 rows)
        rows.append(
            felt_bg() + " " * w_start + RESET +
            w_card[i] +
            felt_bg() + " " * mid_gap + RESET +
            e_card[i] +
            felt_bg() + " " * r_pad + RESET
        )
    rows.append(_felt_blank(center_w))                       # gap
    for line in s_card:                                      # South card (7 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(s_label)                                     # S label
    rows.append(_felt_blank(center_w))                       # bottom padding

    return rows  # 27 rows total


def _render_hand_horizontal(
    cards: tuple[Card, ...],
    selection: int | None,
    legal: tuple[Card, ...],
    term_w: int,
) -> list[str]:
    """Render South's hand horizontally, already centered to term_w.

    The cursor ▲ row is offset to match the visual center of the selected card,
    accounting for the left-padding that ansi_center adds.
    """
    if not cards:
        return [""]

    # Build each card's CARD_H lines
    card_line_groups: list[list[str]] = [
        _card_face(c, selected=(i == selection), legal=(c in legal))
        for i, c in enumerate(cards)
    ]

    # Join cards horizontally with a 1-space gap
    gap = " "
    slot_w = CARD_W + len(gap)          # visible width of one card slot
    total_hand_w = len(cards) * slot_w - len(gap)   # visible width of full hand

    # Compute left padding that ansi_center will add — we need this for the cursor
    left_pad = max(0, (term_w - total_hand_w) // 2)

    rows: list[str] = []
    for row_idx in range(CARD_H):
        raw = gap.join(group[row_idx] for group in card_line_groups)
        rows.append(ansi_center(raw, term_w))   # ← ANSI-aware centering

    # Cursor row — must account for the centering offset so ▲ lands under the card
    if selection is not None:
        cursor_col = left_pad + selection * slot_w + CARD_W // 2
        rows.append(" " * cursor_col + "▲")

    return rows


def _seat_label(seat: Seat, state: GameState) -> str:
    """Colored seat label, highlighted when it's that seat's turn."""
    name = seat.name
    if state.turn == seat:
        return f"{BOLD}{gold_fg()}{name} >>{RESET}"
    return f"{BOLD}{white_fg()}{name}{RESET}"


def _render_middle_section(state: GameState, term_w: int) -> list[str]:
    """Build the 3-column middle section: WEST | green felt mat | EAST."""
    west_hand = state.hand_of(Seat.WEST)
    east_hand = state.hand_of(Seat.EAST)

    center_w = max(0, term_w - SIDE_COL_W * 2)

    # ── Center column (trick area / bidding up-card) ──────────────────────────
    center_rows = []
    if state.phase == Phase.BIDDING and state.up_card:
        # Show the up-card in the center
        up_face = _card_face(state.up_card)
        center_rows = [
            ansi_center(f"{light_gray_fg()}UP CARD{RESET}", 20),
            "",
        ]
        for row in up_face:
            center_rows.append(ansi_center(row, 20))
        center_rows.append("")

        # Pad to match trick mat height if needed (now 27 rows)
        while len(center_rows) < 27:
            center_rows.insert(0, "")
            if len(center_rows) < 27:
                center_rows.append("")
    else:
        trick = state.current_trick
        seat_map: dict[Seat, Card] = {tc.seat: tc.card for tc in trick}
        center_rows = _render_trick_mat(seat_map, center_w)

    n_rows = len(center_rows)

    # ── Left column (WEST) — vertically centred in the mat ───────────────────
    w_label = _seat_label(Seat.WEST, state)
    w_cards = f"{_card_back_small()} " * min(len(west_hand), 4)
    w_count = f"{light_gray_fg()}({len(west_hand)} left){RESET}"

    left_rows: list[str] = [""] * n_rows
    mid = n_rows // 2
    left_rows[mid - 1] = w_label
    left_rows[mid]     = w_cards
    left_rows[mid + 1] = w_count

    # ── Right column (EAST) — vertically centred in the mat ──────────────────
    e_label = _seat_label(Seat.EAST, state)
    e_cards = f"{_card_back_small()} " * min(len(east_hand), 4)
    e_count = f"{light_gray_fg()}({len(east_hand)} left){RESET}"

    right_rows: list[str] = [""] * n_rows
    right_rows[mid - 3] = e_label
    right_rows[mid - 2] = e_cards
    right_rows[mid - 1] = e_count
    
    # Last Trick Panel
    if state.completed_tricks:
        last = state.completed_tricks[-1]
        right_rows[mid + 1] = f"{UNDERLINE}Last Trick:{RESET}"
        # Format as "S:7♠ E:J♦"
        line1 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[:2])
        line2 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[2:])
        right_rows[mid + 2] = line1
        right_rows[mid + 3] = line2

    # ── Combine columns ───────────────────────────────────────────────────────
    result: list[str] = []
    for l, c, r in zip(left_rows, center_rows, right_rows):
        result.append(ansi_ljust(l, SIDE_COL_W) + c + ansi_ljust(r, SIDE_COL_W))

    return result


def _build_hud(state: GameState, term_w: int) -> str:
    """Build the top HUD bar, padded to term_w visible chars."""
    trump_sym  = state.trump.symbol if state.trump else "?"
    ns, ew     = state.team_scores
    trick_num  = len(state.completed_tricks) + (1 if state.current_trick else 0)
    taker_name = state.taker.name if state.taker else "-"

    # Live round points
    ns_pts, ew_pts = state.current_round_points

    left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
    mid  = (f"{white_fg()}Trump: {trump_sym}   "
            f"NS: {BOLD}{ns}{RESET}{white_fg()} (+{ns_pts})   "
            f"EW: {BOLD}{ew}{RESET}{white_fg()} (+{ew_pts})   "
            f"Trick {trick_num}/8   Taker: {taker_name}   "
            f"{DIM}[H]istory [Z]Undo{RESET}")
    bar  = left + "   " + mid
    return ansi_ljust(bar, term_w)


def animate_score_update(state: GameState, target_ns: int, target_ew: int, duration: float = 1.0) -> None:
    """Animate the team scores rolling up to their new values."""
    start_ns, start_ew = state.team_scores
    steps = 20
    delay = duration / steps
    
    for i in range(1, steps + 1):
        curr_ns = start_ns + (target_ns - start_ns) * i // steps
        curr_ew = start_ew + (target_ew - start_ew) * i // steps
        
        temp_state = replace(state, team_scores=(curr_ns, curr_ew))
        display(temp_state, None)
        time.sleep(delay)


def render(state: GameState, selection: int | None = None) -> str:
    """Pure: returns a full-screen ANSI-formatted string. No I/O.

    Terminal width is queried fresh on every call so resizing works correctly.
    """
    # Query terminal size HERE, not at module level.
    term_w, _ = shutil.get_terminal_size(fallback=(120, 40))

    out   = clear_screen() + hide_cursor()
    legal : tuple[Card, ...] = ()
    if state.phase == Phase.PLAYING and state.turn == Seat.SOUTH:
        legal = legal_cards(state, Seat.SOUTH)

    lines: list[str] = []

    # ── HUD ──────────────────────────────────────────────────────────────────
    lines.append(_build_hud(state, term_w))
    lines.append("─" * term_w)

    # ── NORTH ────────────────────────────────────────────────────────────────
    north_hand  = state.hand_of(Seat.NORTH)
    north_cards = f"{_card_back_small()} " * min(len(north_hand), 4)
    north_label = _seat_label(Seat.NORTH, state)
    north_count = f"{light_gray_fg()}({len(north_hand)} cards){RESET}"
    lines.append("")
    lines.append(ansi_center(
        f"{north_label}  {north_cards}  {north_count}", term_w
    ))

    # ── WEST | trick area | EAST  (3-column, same rows) ──────────────────────
    lines.append("")
    for row in _render_middle_section(state, term_w):
        lines.append(row)

    # ── DIVIDER ───────────────────────────────────────────────────────────────
    lines.append("")
    lines.append("─" * term_w)

    # ── PHASE INFO ────────────────────────────────────────────────────────────
    phase_info = ""
    if state.phase == Phase.BIDDING:
        if state.turn == Seat.SOUTH:
            phase_info = f"{BOLD}{gold_fg()}>> YOUR TURN <<{RESET}"
        else:
            phase_info = f"{light_gray_fg()}Waiting for {state.turn.name} to bid...{RESET}"
    elif state.phase == Phase.PLAYING:
        if state.turn == Seat.SOUTH:
            phase_info = f"{BOLD}{gold_fg()}>> YOUR TURN <<{RESET}"
        else:
            phase_info = f"{light_gray_fg()}Waiting for {state.turn.name}...{RESET}"
    elif state.phase == Phase.SCORING:
        phase_info = f"{BOLD}{gold_fg()}Round complete!{RESET}"

    if state.announced:
        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} {state.announced} {RESET}"

    lines.append(ansi_center(phase_info, term_w))
    lines.append("")

    # ── SOUTH hand ────────────────────────────────────────────────────────────
    south_hand  = state.hand_of(Seat.SOUTH)
    south_legal = legal if state.turn == Seat.SOUTH else ()

    if south_hand:
        # Keyboard shortcut hints
        hints = " ".join(f"[{i+1}]" for i in range(len(south_hand)))
        lines.append(ansi_center(hints, term_w))

        # Cards + cursor (already centered inside _render_hand_horizontal)
        for sl in _render_hand_horizontal(south_hand, selection, south_legal, term_w):
            lines.append(sl)

    south_label = _seat_label(Seat.SOUTH, state)
    lines.append(ansi_center(f"{south_label} (you)", term_w))

    # ── BIDDING PROMPT ────────────────────────────────────────────────────────
    if state.phase == Phase.BIDDING and state.turn == Seat.SOUTH:
        lines.append("")
        prompt = f"{BOLD}{gold_fg()}Bid: [P]ass  [1]♠  [2]♥  [3]♦  [4]♣{RESET}"
        lines.append(ansi_center(prompt, term_w))

    # Pad to minimum height to prevent screen flickering
    while len(lines) < 45:
        lines.append("")

    # CRITICAL: use \r\n not \n.
    # tty.setraw() clears OPOST which disables ONLCR (automatic \n→\r\n).
    # Without \r, the cursor moves DOWN but not back to column 1, so every
    # subsequent line starts where the previous one ended — producing the
    # diagonal stagger visible in the screenshot. \r\n fixes this.
    return "".join([out, "\r\n".join(lines), show_cursor()])


def display(state: GameState, selection: int | None = None) -> None:
    sys.stdout.write(render(state, selection))
    sys.stdout.flush()


def prompt_card(state: GameState, reader: KeyReader) -> Card | None:
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
                    return hand[sel]
                # Fallback: return nearest legal card
                for delta in range(1, len(hand)):
                    for d in (delta, -delta):
                        idx = sel + d
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            return hand[idx]
            case Key.CHAR:
                if event.char:
                    char = event.char.lower()
                    if char == 'h':
                        show_history(state, reader)
                        continue
                    if char == 'z':
                        return "UNDO" # type: ignore[return-value]
                    if char.isdigit():
                        idx = int(char) - 1
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            return hand[idx]


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
        term_w, _ = shutil.get_terminal_size(fallback=(120, 40))
        
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
            case Key.CHAR:
                if event.char:
                    char = event.char.lower()
                    if char == 'h':
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
            
        lines.append(f"{DIM}Press [T] to Toggle Language ({l.upper()}) | [Q/Enter] Back{RESET}")
        cached_renders[l] = lines
        return lines

    while True:
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
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
            case Key.UP:
                scroll = max(0, scroll - 1)
            case Key.DOWN:
                scroll = min(len(all_lines) - view_h, scroll + 1)
            case Key.CHAR:
                if event.char and event.char.lower() == 't':
                    lang = "fr" if lang == "en" else "en"
                    scroll = 0


CARDS_ART = [
    f"      {white_fg()}⢠⣴⣶⣶⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
    f"      {white_fg()}⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
    f"     {white_fg()}⢰⣿⣿⣿⣿⡿⠟⠁⣠⣴⣶⣦⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
    f"     {white_fg()}⢸⣿⣿⠟⠉⣠⣴⣿⣿⣿⠟⠁⣠⣾⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀{RESET}",
    f"      {white_fg()}⠉⣀⣴⣾⣿⣿⣿⠟⢁⣤⣾⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀{RESET}",
    f"    {white_fg()}⢀⣤⣾⣿⣿⣿⡿⠛⢁⣴⣿⣿⣿⣿⣿⣿⣿⠟⠁⡀⠀⠀⠀⠀⠀{RESET}",
    f"    {white_fg()}⢼⣿⣿⣿⡿⠋⣀⣴⣿⣿⣿⣿⣿⣿⣿⡿⠉⣠⣾⣿⡆⠀⠀⠀⠀{RESET}",
    f"    {white_fg()}⠘⢿⡿⠋⣠⣾⣿⣿⣿⠟⠁⣿⣿⣿⣿⣿⠟⢁⣀⠀⠀⠀{RESET}",
    f"      {white_fg()}⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⠏⢀⣴⣿⣿⣿⠋⢠⣾⣿⣷⣦⡀{RESET}",
    f"      {white_fg()}⢻⣿⣿⣿⣿⣿⣿⣿⠟⢁⣴⣿⣿⣿⡿⠁⣰⣿⣿⣿⣿⣿⣿{RESET}",
    f"       {white_fg()}⠹⢿⣿⣿⣿⡿⠋⣠⣾⣿⣿⣿⠟⢀⣼⣿⣿⣿⣿⣿⣿⡟{RESET}",
    f"         {white_fg()}⠉⠉⠉⠀⢾⣿⣿⣿⣿⠋⠀⠚⠛⠛⠛⠛⠛⠛⠁⠀{RESET}",
]

CUP_TEMPLATE = [
    "                       {steam0}",
    "                        {steam1}",
    "                 {gold}___...(-------)-....___{reset}",
    "             {gold}.-''       )    (          ''-.{reset}",
    "       {gold}.-'``'|-._             )         _.-|{reset}",
    "      {gold}/  .--.|   `''---...........---''`   |{reset}",
    "     {gold}/  /    |  {opt0}                |{reset}",
    "     {gold}|  |    |  {opt1}                |{reset}",
    "      {gold}\\  \\   |  {opt2}                |{reset}",
    "       {gold}`\\ `\\ |  {opt3}                |{reset}",
    "         {gold}`\\ `|  {opt4}                |{reset}",
    "         {gold}_/ /\\  {opt5}                /{reset}",
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
    ("     (       ", "      )     (", "     (       ")
]

def _render_main_menu_art(sel: int, options: list[str], frame: int) -> list[str]:
    """Render the full main menu art with cards logo and chalice container."""
    f = frame % 4
    st = STEAMS[f]
    
    # Process placeholders
    opts = {}
    for i in range(6):
        label = options[i] if i < len(options) else ""
        if i == sel:
            text = f"{REVERSE} > {label} < {RESET}"
        else:
            text = f"  {label}  "
        opts[f"opt{i}"] = ansi_center(text, 29)

    final_cup = []
    for line in CUP_TEMPLATE:
        final_cup.append(line.format(
            steam0=f"{white_fg()}{st[0]}{RESET}",
            steam1=f"{white_fg()}{st[1]}{RESET}",
            gold=gold_fg(),
            reset=RESET,
            **opts
        ))

    return CARDS_ART + [""] + final_cup


def show_ai_config(reader: KeyReader, current_diffs: dict[Seat, str]) -> dict[Seat, str]:
    """Configure AI difficulty per seat."""
    sel = 0
    seats = [Seat.EAST, Seat.NORTH, Seat.WEST]
    diffs = ["easy", "medium", "hard"]
    
    while True:
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        
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


def show_main_menu(reader: KeyReader, diffs_map: dict[Seat, str], target: int, speed: str, mode: str) -> tuple[str, dict[Seat, str], int, str, str]:
    """Display the main menu and return (choice, diffs_map, target, speed, mode)."""
    curr_target = target
    curr_speed = speed
    curr_mode = mode
    curr_diffs = diffs_map
    
    sel = 0
    targs = [500, 1000, 1500, 2000]
    spds = ["slow", "normal", "fast", "instant"]
    modes = ["Single Player", "Hotseat (2P)"]
    frame = 0

    while True:
        # Determine display difficulty
        unique_diffs = set(curr_diffs.values())
        if len(unique_diffs) == 1:
            diff_display = next(iter(unique_diffs)).capitalize()
        else:
            diff_display = "Mixed"

        options_labels = [
            "Start Game",
            f"Mode:         < {curr_mode} >",
            f"AI Config:     < {diff_display} >",
            f"Target Score: < {curr_target} >",
            f"Speed:        < {curr_speed.capitalize()} >",
            "Rules & History",
            "Statistics",
            "Quit"
        ]
        
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        out = clear_screen() + hide_cursor()
        
        # Build the art containing the menu
        all_lines = _render_main_menu_art(sel, options_labels, frame)
        
        # Center the entire block vertically and horizontally
        v_pad = max(0, (term_h - len(all_lines) - 2) // 2)
        
        lines = [""] * v_pad
        for line in all_lines:
            lines.append(ansi_center(line, term_w))
        
        lines.append("")
        lines.append(ansi_center(f"{light_gray_fg()}↑/↓: Navigate  ←/→: Change Settings  Enter: Confirm/Config  Q: Quit{RESET}", term_w))
        
        sys.stdout.write(out + "\r\n".join(lines))
        sys.stdout.flush()
        
        event = reader.read_timeout(0.3)
        if event is None:
            frame += 1
            continue

        match event.key:
            case Key.QUIT:
                return "Quit", curr_diffs, curr_target, curr_speed, curr_mode
            case Key.UP:
                sel = (sel - 1) % len(options_labels)
            case Key.DOWN:
                sel = (sel + 1) % len(options_labels)
            case Key.LEFT | Key.RIGHT:
                delta = 1 if event.key == Key.RIGHT else -1
                if sel == 1:
                    curr_mode = modes[(modes.index(curr_mode) + delta) % len(modes)]
                elif sel == 2:
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
            case Key.ENTER:
                choice = ["Start Game", "Mode", "AI Config", "Target Score", "Speed", "Rules & History", "Statistics", "Quit"][sel]
                if choice == "AI Config":
                    curr_diffs = show_ai_config(reader, curr_diffs)
                    continue
                if choice in ("Start Game", "Quit", "Rules & History", "Statistics"):
                    return choice, curr_diffs, curr_target, curr_speed, curr_mode
                # For settings, Enter can also toggle forward
                if sel == 1:
                    curr_mode = modes[(modes.index(curr_mode) + 1) % len(modes)]
                elif sel == 3:
                    curr_target = targs[(targs.index(curr_target) + 1) % len(targs)]
                elif sel == 4:
                    curr_speed = spds[(spds.index(curr_speed) + 1) % len(spds)]


def show_history(state: GameState, reader: KeyReader) -> None:
    """Display a scrollable overlay of round-by-round scores."""
    scroll = 0
    
    while True:
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        
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
        return  # Any key returns


def announce(message: str, duration: float = 2.0) -> None:
    """Display a transient announcement banner."""
    sys.stdout.write(f"\r\n{banner_bg()}{banner_fg()}  {BOLD} {message} {RESET}\r\n")
    sys.stdout.flush()
    time.sleep(duration)

def play_sound(kind: str) -> None:
    """Simple terminal sounds using bell."""
    # We can use multiple bells or other tricks for different sounds
    if kind == "trick":
        sys.stdout.write("\a")
    elif kind == "belote":
        sys.stdout.write("\a\a")
    elif kind == "chute":
        sys.stdout.write("\a\a\a")
    elif kind == "capot":
        sys.stdout.write("\a\a\a\a\a")
    sys.stdout.flush()


from .stats import load_stats


def show_stats(reader: KeyReader) -> None:
    """Display global game statistics."""
    stats = load_stats()
    
    while True:
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        
        lines = []
        lines.append(f"{BOLD}{gold_fg()}GLOBAL STATISTICS{RESET}")
        lines.append("=" * 17)
        lines.append("")
        
        lines.append(f"  Games Played:        {stats.games_played}")
        lines.append(f"  Games Won:           {stats.games_won}")
        win_rate = (stats.games_won / stats.games_played * 100) if stats.games_played > 0 else 0
        lines.append(f"  Win Rate:            {win_rate:.1f}%")
        lines.append("")
        lines.append(f"  Total Rounds:        {stats.total_rounds}")
        lines.append(f"  Avg Pts per Round:   {(stats.total_points_scored / stats.total_rounds if stats.total_rounds > 0 else 0):.1f}")
        lines.append("")
        lines.append(f"  Capots Achieved:     {stats.capots_achieved}")
        lines.append(f"  Max Capot Streak:    {stats.max_capot_streak}")
        lines.append("")
        lines.append(f"{DIM}Press [Any Key] to Return{RESET}")

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()
        
def show_final_screen(state: GameState) -> None:
    """Display the game-over screen."""
    ns, ew = state.team_scores
    if ns >= state.target and ew >= state.target:
        winner = "NS" if ns > ew else "EW"
    elif ns >= state.target:
        winner = "NS"
    else:
        winner = "EW"

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
