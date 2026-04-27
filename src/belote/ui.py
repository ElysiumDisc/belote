from __future__ import annotations

import shutil
import sys
import time

from .deck import Card, Rank, Suit
from .game import (
    GameState,
    Phase,
    Seat,
    TrickCard,
    legal_cards,
    team_of,
    partner,
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


# Card display dimensions — fixed constants only, no terminal queries at module level.
# Terminal width is queried fresh inside render() on every frame.
CARD_W = 6
CARD_H = 5
CARD_GAP = 1

# Fixed visible width for the WEST and EAST side columns in the middle section.
SIDE_COL_W = 22


def _card_symbol(card: Card) -> str:
    return f"{card.rank.value}{card.suit.symbol}"


def _card_face(card: Card, selected: bool = False, legal: bool = True) -> list[str]:
    """Render a card as CARD_H lines of width CARD_W."""
    sym = card.rank.value + " " if len(card.rank.value) == 1 else card.rank.value
    suit_sym = card.suit.symbol
    face_text = f"{sym}{suit_sym}"

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
    
    # Optional miniature art for face cards
    art = "  "
    if card.rank == Rank.JACK:
        art = "⚔ "
    elif card.rank == Rank.QUEEN:
        art = "♕ "
    elif card.rank == Rank.KING:
        art = "♔ "
    elif card.rank == Rank.ACE:
        art = "★ "

    return [
        f"{prefix}{bg_code}{color}┌{'─' * inner_w}┐{RESET}",
        f"{prefix}{bg_code}{color}│{face_text.ljust(inner_w)}│{RESET}",
        f"{prefix}{bg_code}{color}│{art.center(inner_w)}│{RESET}",
        f"{prefix}{bg_code}{color}│{face_text.rjust(inner_w)}│{RESET}",
        f"{prefix}{bg_code}{color}└{'─' * inner_w}┘{RESET}",
    ]


def _card_back() -> list[str]:
    """Render a face-down card."""
    inner_w = CARD_W - 2
    hatch = "╳" * (inner_w // 2)
    return [
        f"{card_back_bg()}┌{'─' * inner_w}┐{RESET}",
        f"{card_back_bg()}│{' ' * inner_w}│{RESET}",
        f"{card_back_bg()}│{hatch.center(inner_w)}│{RESET}",
        f"{card_back_bg()}│{' ' * inner_w}│{RESET}",
        f"{card_back_bg()}└{'─' * inner_w}┘{RESET}",
    ]


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
    return [top, mid, mid, mid, bottom]


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
    for line in n_card:                                      # North card (5 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(_felt_blank(center_w))                       # gap
    for i in range(CARD_H):                                  # West + East (5 rows)
        rows.append(
            felt_bg() + " " * w_start + RESET +
            w_card[i] +
            felt_bg() + " " * mid_gap + RESET +
            e_card[i] +
            felt_bg() + " " * r_pad + RESET
        )
    rows.append(_felt_blank(center_w))                       # gap
    for line in s_card:                                      # South card (5 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(s_label)                                     # S label
    rows.append(_felt_blank(center_w))                       # bottom padding

    return rows  # 21 rows total


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
            ansi_center(f"{BOLD}{white_fg()}ROUND {state.bidding_round}{RESET}", 20),
            "",
            ansi_center(up_face[0], 20),
            ansi_center(up_face[1], 20),
            ansi_center(up_face[2], 20),
            ansi_center(up_face[3], 20),
            ansi_center(up_face[4], 20),
            "",
        ]
        # Pad to match trick mat height if needed
        while len(center_rows) < 21: # Trick mat is 21 rows
            center_rows.insert(0, "")
            if len(center_rows) < 21:
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
    ns_round = state.tricks_won_by_team(0)  # We'll need to count points instead of tricks
    ew_round = state.tricks_won_by_team(1)
    
    # Actually calculate card points for better 'live' feel
    from .deck import card_points
    ns_pts = 0
    ew_pts = 0
    for trick in state.completed_tricks:
        from .game import trick_winner_seat, team_of
        winner = trick_winner_seat(trick, state.trump)
        p = sum(card_points(tc.card, state.trump) for tc in trick)
        if winner and team_of(winner) == 0:
            ns_pts += p
        elif winner:
            ew_pts += p
            
    # Include Dix de Der in live score if 8 tricks are done
    if len(state.completed_tricks) == 8:
        from .game import trick_winner_seat, team_of
        winner = trick_winner_seat(state.completed_tricks[-1], state.trump)
        if winner and team_of(winner) == 0:
            ns_pts += 10
        elif winner:
            ew_pts += 10

    left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
    mid  = (f"{white_fg()}Trump: {trump_sym}   "
            f"NS: {BOLD}{ns}{RESET}{white_fg()} (+{ns_pts})   "
            f"EW: {BOLD}{ew}{RESET}{white_fg()} (+{ew_pts})   "
            f"Trick {trick_num}/8   Taker: {taker_name}{RESET}")
    bar  = left + "   " + mid
    return ansi_ljust(bar, term_w)


def animate_score_update(state: GameState, target_ns: int, target_ew: int, duration: float = 1.0) -> None:
    """Animate the team scores rolling up to their new values."""
    import time
    from .game import replace
    
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

    # Pad to minimum height
    while len(lines) < 26:
        lines.append("")

    # CRITICAL: use \r\n not \n.
    # tty.setraw() clears OPOST which disables ONLCR (automatic \n→\r\n).
    # Without \r, the cursor moves DOWN but not back to column 1, so every
    # subsequent line starts where the previous one ended — producing the
    # diagonal stagger visible in the screenshot. \r\n fixes this.
    return out + "\r\n".join(lines) + show_cursor()


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
                if event.char and event.char.isdigit():
                    idx = int(event.char) - 1
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
                    if event.char.lower() == 'p':
                        return None
                    try:
                        idx = int(event.char) - 1
                        if 0 <= idx < len(options):
                            return options[idx]
                    except ValueError:
                        pass


def show_rules(reader: KeyReader) -> None:
    """Display scrollable rules and history in EN/FR."""
    from .rules import RULES_CONTENT
    lang = "en"
    scroll = 0
    
    while True:
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        content = RULES_CONTENT[lang]
        
        # Build all lines first
        all_lines = []
        all_lines.append(f"{BOLD}{gold_fg()}{content['title']}{RESET}")
        all_lines.append("=" * visible_len(content['title']))
        all_lines.append("")
        
        for section in content['sections']:
            all_lines.append(f"{BOLD}{white_fg()}{section['header']}{RESET}")
            all_lines.append("-" * len(section['header']))
            # Wrap text manually
            words = section['text'].split()
            line = "  "
            for w in words:
                if len(line) + len(w) > 70:
                    all_lines.append(line)
                    line = "  " + w + " "
                else:
                    line += w + " "
            all_lines.append(line)
            all_lines.append("")
            
        all_lines.append(f"{DIM}Press [T] to Toggle Language ({lang.upper()}) | [Q/Enter] Back{RESET}")

        # Window the lines
        view_h = term_h - 4
        scroll = max(0, min(scroll, len(all_lines) - view_h))
        visible_lines = all_lines[scroll : scroll + view_h]
        
        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible_lines)
        sys.stdout.write(out + rendered)
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


def _render_main_menu_art(sel: int, options: list[str], frame: int) -> list[str]:
    """Render the full main menu art with cards logo and chalice container."""
    f = frame % 4
    # Steam frames
    steams = [
        ("      (      ", "       )     (", "      (      "),
        ("       )     ", "      (      )", "       )     "),
        ("      (      ", "       )     (", "      (      "),
        ("     (       ", "      )     (", "     (       ")
    ]
    st = steams[f]
    
    g = gold_fg()
    w = white_fg()
    
    cards_art = [
        f"      {w}⢠⣴⣶⣶⣶⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"      {w}⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"     {w}⢰⣿⣿⣿⣿⡿⠟⠁⣠⣴⣶⣦⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"     {w}⢸⣿⣿⠟⠉⣠⣴⣿⣿⣿⠟⠁⣠⣾⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀{RESET}",
        f"      {w}⠉⣀⣴⣾⣿⣿⣿⠟⢁⣤⣾⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀{RESET}",
        f"    {w}⢀⣤⣾⣿⣿⣿⡿⠛⢁⣴⣿⣿⣿⣿⣿⣿⣿⠟⠁⡀⠀⠀⠀⠀⠀{RESET}",
        f"    {w}⢼⣿⣿⣿⡿⠋⣀⣴⣿⣿⣿⣿⣿⣿⣿⡿⠉⣠⣾⣿⡆⠀⠀⠀⠀{RESET}",
        f"    {w}⠘⢿⡿⠋⣠⣾⣿⣿⣿⠟⠁⣿⣿⣿⣿⣿⠟⢁⣀⠀⠀⠀{RESET}",
        f"      {w}⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⠏⢀⣴⣿⣿⣿⠋⢠⣾⣿⣷⣦⡀{RESET}",
        f"      {w}⢻⣿⣿⣿⣿⣿⣿⣿⠟⢁⣴⣿⣿⣿⡿⠁⣰⣿⣿⣿⣿⣿⣿{RESET}",
        f"       {w}⠹⢿⣿⣿⣿⡿⠋⣠⣾⣿⣿⣿⠟⢀⣼⣿⣿⣿⣿⣿⣿⡟{RESET}",
        f"         {w}⠉⠉⠉⠀⢾⣿⣿⣿⣿⠋⠀⠚⠛⠛⠛⠛⠛⠛⠁⠀{RESET}",
    ]

    # The Vessel / Chalice frame template
    cup = [
        f"                       {w}{st[0]}{RESET}",
        f"                        {w}{st[1]}{RESET}",
        f"                 {g}___...(-------)-....___{RESET}",
        f"             {g}.-''       )    (          ''-.{RESET}",
        f"       {g}.-'``'|-._             )         _.-|{RESET}",
        f"      {g}/  .--.|   `''---...........---''`   |{RESET}",
        f"     {g}/  /    |  [[ OPT 0 ]]                |{RESET}",
        f"     {g}|  |    |  [[ OPT 1 ]]                |{RESET}",
        f"      {g}\\  \\   |  [[ OPT 2 ]]                |{RESET}",
        f"       {g}`\\ `\\ |  [[ OPT 3 ]]                |{RESET}",
        f"         {g}`\\ `|  [[ OPT 4 ]]                |{RESET}",
        f"         {g}_/ /\\  [[ OPT 5 ]]                /{RESET}",
        f"        {g}(__/  \\                           /{RESET}",
        f"     {g}_..---''` \\                         /`''---.._{RESET}",
        f"  {g}.-'           \\                       /          '-.{RESET}",
        f" {g}:               `-.__             __.-'              :{RESET}",
        f" {g}:                  ) ''---...---'' (                 :{RESET}",
        f"  {g}'._               `''...___...--''`              _.'{RESET}",
        f" {g}jgs \\''--..__                              __..--''/{RESET}",
        f"     {g}'._     '''----.....______.....----'''     _.'{RESET}",
        f"        {g}`''--..,,_____            _____,,..--''`{RESET}",
        f"                      {g}`'''----'''`{RESET}",
    ]

    # Process placeholders
    final_cup = []
    for line in cup:
        new_line = line
        for i in range(6):
            tag = f"[[ OPT {i} ]]"
            if tag in line:
                label = options[i] if i < len(options) else ""
                if i == sel:
                    text = f"{REVERSE} > {label} < {RESET}"
                else:
                    text = f"  {label}  "
                # Center text in a fixed 29-character wide field
                centered = ansi_center(text, 29)
                new_line = line.replace(tag, centered)
        final_cup.append(new_line)

    return cards_art + [""] + final_cup


def show_main_menu(reader: KeyReader, difficulty: str, target: int, speed: str) -> tuple[str, str, int, str]:
    """Display the main menu and return (choice, difficulty, target, speed)."""
    curr_diff = difficulty
    curr_target = target
    curr_speed = speed
    
    sel = 0
    diffs = ["easy", "medium", "hard"]
    targs = [500, 1000, 1500, 2000]
    spds = ["slow", "normal", "fast", "instant"]
    frame = 0

    while True:
        options_labels = [
            "Start Game",
            f"Difficulty:   < {curr_diff.capitalize()} >",
            f"Target Score: < {curr_target} >",
            f"Speed:        < {curr_speed.capitalize()} >",
            "Rules & History",
            "Quit"
        ]
        
        term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
        out = clear_screen() + hide_cursor()
        
        # Build the art containing the menu
        all_lines = _render_main_menu_art(sel, options_labels, frame)
        
        # Center the entire block vertically and horizontally
        v_pad = max(0, (term_h - len(all_lines) - 2) // 2)
        h_pad = "" # Horizontal centering handled by ansi_center within _render
        
        lines = [""] * v_pad
        for line in all_lines:
            lines.append(ansi_center(line, term_w))
        
        lines.append("")
        lines.append(ansi_center(f"{light_gray_fg()}↑/↓: Navigate  ←/→: Change Settings  Enter: Confirm  Q: Quit{RESET}", term_w))
        
        sys.stdout.write(out + "\r\n".join(lines))
        sys.stdout.flush()
        
        event = reader.read_timeout(0.3)
        if event is None:
            frame += 1
            continue

        match event.key:
            case Key.QUIT:
                return "Quit", curr_diff, curr_target, curr_speed
            case Key.UP:
                sel = (sel - 1) % len(options_labels)
            case Key.DOWN:
                sel = (sel + 1) % len(options_labels)
            case Key.LEFT | Key.RIGHT:
                delta = 1 if event.key == Key.RIGHT else -1
                if sel == 1:
                    curr_diff = diffs[(diffs.index(curr_diff) + delta) % len(diffs)]
                elif sel == 2:
                    curr_target = targs[(targs.index(curr_target) + delta) % len(targs)]
                elif sel == 3:
                    curr_speed = spds[(spds.index(curr_speed) + delta) % len(spds)]
            case Key.ENTER:
                choice = ["Start Game", "Difficulty", "Target Score", "Speed", "Rules & History", "Quit"][sel]
                if choice in ("Start Game", "Quit", "Rules & History"):
                    return choice, curr_diff, curr_target, curr_speed
                # For settings, Enter can also toggle forward
                if sel == 1:
                    curr_diff = diffs[(diffs.index(curr_diff) + 1) % len(diffs)]
                elif sel == 2:
                    curr_target = targs[(targs.index(curr_target) + 1) % len(targs)]
                elif sel == 3:
                    curr_speed = spds[(spds.index(curr_speed) + 1) % len(spds)]


def announce(message: str, duration: float = 2.0) -> None:
    """Display a transient announcement banner."""
    import time
    sys.stdout.write(f"\n{banner_bg()}{banner_fg()}  {BOLD} {message} {RESET}\n")
    sys.stdout.flush()
    time.sleep(duration)


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
        f"  {light_gray_fg()}Press Enter to exit{RESET}",
    ]

    sys.stdout.write(clear_screen())
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()
