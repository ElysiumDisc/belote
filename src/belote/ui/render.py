from __future__ import annotations

import signal
import sys
from functools import lru_cache
from typing import Final

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    UNDERLINE,
    ansi_center,
    ansi_ljust,
    black_fg,
    card_back_bg,
    card_face_bg,
    clear_to_eol,
    face_card_bg,
    felt_bg,
    felt_placeholder_fg,
    gold_fg,
    hide_cursor,
    highlight_bg,
    light_gray_fg,
    move,
    red_fg,
    show_cursor,
    visible_len,
    white_fg,
)
from ..config import GLOBAL_CONFIG
from ..context import TERMINAL
from ..deck import Card, Rank
from ..game import (
    GameState,
    Phase,
    Seat,
    legal_cards,
)
from ..themes import theme_manager

# ── UI Constants ─────────────────────────────────────────────────────────────
# Card display dimensions — from GLOBAL_CONFIG
CARD_W = GLOBAL_CONFIG.CARD_W
CARD_H = GLOBAL_CONFIG.CARD_H
CARD_GAP = GLOBAL_CONFIG.CARD_GAP

# Fixed visible width for the WEST and EAST side columns in the middle section.
SIDE_COL_W = 22

# Vertical offsets within the trick mat for each seat (relative to mat top)
_TRICK_ROW_OFFSETS: Final = {
    Seat.NORTH: 2,
    Seat.WEST: 10,
    Seat.EAST: 10,
    Seat.SOUTH: 18,
}


def get_term_size() -> tuple[int, int]:
    """Get terminal size, using cached value if available."""
    return TERMINAL.get_size()


def _handle_sigwinch(_signum: int, _frame: object) -> None:
    """Invalidate terminal size cache on resize."""
    TERMINAL.clear_cache()


if hasattr(signal, "SIGWINCH"):
    signal.signal(signal.SIGWINCH, _handle_sigwinch)


def _card_symbol(card: Card) -> str:

    suit_str = card.suit.symbol if TERMINAL.has_utf8 else card.suit.name[0]
    return f"{card.rank.value}{suit_str}"


@lru_cache(maxsize=1024)
def _card_face_internal(
    card: Card, selected: bool, legal: bool, theme_name: str, has_utf8: bool
) -> list[str]:
    """Render a card as CARD_H lines of width CARD_W with Art Nouveau styling (cached)."""
    rank_str = card.rank.value
    suit_sym = card.suit.symbol if has_utf8 else card.suit.name[0]

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
        art_top = "  ▄▆▄  " if has_utf8 else "  ***  "
        art_mid = f"  {suit_sym}V{suit_sym}  "
        art_bot = "  ▀▆▀  " if has_utf8 else "  ***  "
    elif card.rank == Rank.QUEEN:
        art_top = "  ╭▼╮  " if has_utf8 else "  ( )  "
        art_mid = f"  {suit_sym}Q{suit_sym}  "
        art_bot = "  ╰─╯  " if has_utf8 else "  ---  "
    elif card.rank == Rank.KING:
        art_top = "  ╔█╗  " if has_utf8 else "  [#]  "
        art_mid = f"  {suit_sym}K{suit_sym}  "
        art_bot = "  ╚═╝  " if has_utf8 else "  [=]  "
    elif card.rank == Rank.ACE:
        art_top = "   ▲   " if has_utf8 else "   ^   "
        art_mid = f"  {suit_sym}A{suit_sym}  "
        art_bot = "   ▼   " if has_utf8 else "   v   "
    else:
        # Pips for numbered cards - simplified but elegant
        art_mid = f"   {suit_sym}   "

    # Use ornate border characters
    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )

    return [
        f"{prefix}{bg_code}{color}{b_tl}{b_h * inner_w}{b_tr}{RESET}",
        f"{prefix}{bg_code}{color}{b_v}{tl_rank}{' ' * (inner_w - 2)}{b_v}{RESET}",
        f"{prefix}{bg_code}{color}{b_v}{art_top}{b_v}{RESET}",
        f"{prefix}{bg_code}{color}{b_v}{art_mid}{b_v}{RESET}",
        f"{prefix}{bg_code}{color}{b_v}{art_bot}{b_v}{RESET}",
        f"{prefix}{bg_code}{color}{b_v}{' ' * (inner_w - 2)}{br_rank}{b_v}{RESET}",
        f"{prefix}{bg_code}{color}{b_bl}{b_h * inner_w}{b_br}{RESET}",
    ]


def _get_card_face(card: Card, selected: bool = False, legal: bool = True) -> list[str]:
    """Helper to call cached _card_face with current global state."""
    return _card_face_internal(
        card, selected, legal, theme_manager._current_theme_name, TERMINAL.has_utf8
    )


def clear_card_cache() -> None:
    """Clear the card face render cache. Call after changing the active theme."""
    _card_face_internal.cache_clear()


# Register callback to clear cache when theme changes
theme_manager.register_callback(clear_card_cache)


@lru_cache(maxsize=128)
def _card_back(theme_name: str, has_utf8: bool) -> list[str]:
    """Render a face-down card with an ornate pattern."""
    inner_w = CARD_W - 2
    # Decorative lattice pattern for the back
    pattern = [
        " ░▒▓▒░ " if has_utf8 else " XXXXX ",
        " ░▒▓▒░ " if has_utf8 else " XXXXX ",
        " ░▒▓▒░ " if has_utf8 else " XXXXX ",
        " ░▒▓▒░ " if has_utf8 else " XXXXX ",
        " ░▒▓▒░ " if has_utf8 else " XXXXX ",
    ]

    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )

    res = [f"{card_back_bg()}{b_tl}{b_h * inner_w}{b_tr}{RESET}"]
    for line in pattern:
        res.append(f"{card_back_bg()}{b_v}{line}{b_v}{RESET}")
    res.append(f"{card_back_bg()}{b_bl}{b_h * inner_w}{b_br}{RESET}")
    return res


def _get_card_back() -> list[str]:
    return _card_back(theme_manager._current_theme_name, TERMINAL.has_utf8)


def _card_back_small() -> str:
    """Single-line face-down card for opponent hand display."""
    char = "▓▓" if TERMINAL.has_utf8 else "[]"
    return f"{card_back_bg()}{char}{RESET}"


@lru_cache(maxsize=32)
def _felt_blank_internal(width: int, theme_name: str) -> str:
    return felt_bg() + " " * width + RESET


def _get_felt_blank(width: int) -> str:
    return _felt_blank_internal(width, theme_manager._current_theme_name)


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
    dim = felt_placeholder_fg()
    top = felt_bg() + dim + "┌" + "─" * inner_w + "┐" + RESET
    mid = felt_bg() + dim + "│" + " " * inner_w + "│" + RESET
    bottom = felt_bg() + dim + "└" + "─" * inner_w + "┘" + RESET
    return [top] + [mid] * (CARD_H - 2) + [bottom]


def _render_trick_mat(seat_map: dict[Seat, Card], center_w: int) -> list[str]:
    """21-row green felt mat with full card graphics at compass positions."""

    def slot(seat: Seat) -> list[str]:
        return _get_card_face(seat_map[seat]) if seat in seat_map else _felt_placeholder()

    n_card = slot(Seat.NORTH)
    w_card = slot(Seat.WEST)
    e_card = slot(Seat.EAST)
    s_card = slot(Seat.SOUTH)

    # Horizontal anchors: West centred at ¼, East centred at ¾ of center_w
    w_start = max(0, center_w // 4 - CARD_W // 2)
    e_start = max(0, 3 * center_w // 4 - CARD_W // 2)
    mid_gap = max(0, e_start - w_start - CARD_W)
    r_pad = max(0, center_w - e_start - CARD_W)

    n_label = _felt_pad(f"{light_gray_fg()}N{RESET}", center_w)
    s_label = _felt_pad(f"{light_gray_fg()}S{RESET}", center_w)

    rows: list[str] = []

    rows.append(_get_felt_blank(center_w))  # top padding
    rows.append(n_label)  # N label
    for line in n_card:  # North card (7 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(_get_felt_blank(center_w))  # gap
    for i in range(CARD_H):  # West + East (7 rows)
        rows.append(
            felt_bg()
            + " " * w_start
            + RESET
            + w_card[i]
            + felt_bg()
            + " " * mid_gap
            + RESET
            + e_card[i]
            + felt_bg()
            + " " * r_pad
            + RESET
        )
    rows.append(_get_felt_blank(center_w))  # gap
    for line in s_card:  # South card (7 rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(s_label)  # S label
    rows.append(_get_felt_blank(center_w))  # bottom padding

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
    legal_set = set(legal)
    card_line_groups: list[list[str]] = [
        _get_card_face(c, selected=(i == selection), legal=(c in legal_set))
        for i, c in enumerate(cards)
    ]

    # Join cards horizontally with a 1-space gap
    gap = " "
    slot_w = CARD_W + len(gap)  # visible width of one card slot
    total_hand_w = len(cards) * slot_w - len(gap)  # visible width of full hand

    # Compute left padding that ansi_center will add — we need this for the cursor
    left_pad = max(0, (term_w - total_hand_w) // 2)

    rows: list[str] = []
    for row_idx in range(CARD_H):
        raw = gap.join(group[row_idx] for group in card_line_groups)
        rows.append(ansi_center(raw, term_w))  # ← ANSI-aware centering

    # Cursor row — must account for the centering offset so ▲ lands under the card
    if selection is not None:
        cursor_col = left_pad + selection * slot_w + CARD_W // 2
        rows.append(" " * cursor_col + "▲")

    return rows


def _seat_label(seat: Seat, state: GameState) -> str:
    """Colored seat label, highlighted when it's that seat's turn."""
    if seat == Seat.SOUTH:
        name = "You"
    elif seat == Seat.NORTH:
        name = "Partner"
    else:
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
        up_face = _get_card_face(state.up_card)
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
    left_rows[mid] = w_cards
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
        # Use simple underline if UNDERLINE is not imported correctly, but here it is.
        # Format as "S:7♠ E:J♦"
        line1 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[:2])
        line2 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[2:])
        right_rows[mid + 2] = line1
        right_rows[mid + 3] = line2

    # ── Combine columns ───────────────────────────────────────────────────────
    result: list[str] = []
    for left, c, r in zip(left_rows, center_rows, right_rows, strict=False):
        result.append(ansi_ljust(left, SIDE_COL_W) + c + ansi_ljust(r, SIDE_COL_W))

    return result


def _build_hud(state: GameState, term_w: int) -> str:
    """Build the top HUD bar, padded to term_w visible chars."""
    if state.boss_modifiers.hide_hud:
        left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
        mid = f"{DIM} [HUD HIDDEN BY BOSS] {RESET}"
        theme_label = f"{DIM}Theme: {theme_manager.get_current().name}{RESET}"
        bar = left + "   " + mid
        vlen_bar = visible_len(bar)
        vlen_theme = visible_len(theme_label)
        pad = max(0, term_w - vlen_bar - vlen_theme - 1)
        return bar + " " * pad + theme_label

    trump_sym = state.trump.symbol if state.trump else "?"
    ns, ew = state.team_scores
    trick_num = len(state.completed_tricks) + (1 if state.current_trick else 0)
    taker_name = state.taker.name if state.taker else "-"

    # Live round points
    ns_pts, ew_pts = state.current_round_points

    left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
    theme_label = f"{DIM}Theme: {theme_manager.get_current().name}{RESET}"
    mid = (
        f"{white_fg()}Trump: {trump_sym}   "
        f"NS: {BOLD}{ns}{RESET}{white_fg()} (+{ns_pts})   "
        f"EW: {BOLD}{ew}{RESET}{white_fg()} (+{ew_pts})   "
        f"Trick {trick_num}/8   Taker: {taker_name}   "
        f"{DIM}[T]History [Z]Undo [S-T]Theme{RESET}"
    )
    bar = left + "   " + mid

    # Right-align theme name
    vlen_bar = visible_len(bar)
    vlen_theme = visible_len(theme_label)
    pad = max(0, term_w - vlen_bar - vlen_theme - 1)

    return bar + " " * pad + theme_label


def render(state: GameState, selection: int | None = None, show_north_hand: bool = False) -> str:
    """Pure: returns a full-screen ANSI-formatted string. No I/O.

    Terminal width is queried fresh on every call so resizing works correctly.
    """
    # Query terminal size HERE, not at module level.
    term_w, term_h = get_term_size()

    out = move(1, 1) + hide_cursor()
    legal: tuple[Card, ...] = ()
    if state.phase == Phase.PLAYING and state.turn == Seat.SOUTH:
        legal = legal_cards(state, Seat.SOUTH)

    lines: list[str] = []

    # ── HUD ──────────────────────────────────────────────────────────────────
    lines.append(_build_hud(state, term_w))
    lines.append("─" * term_w)

    # ── NORTH ────────────────────────────────────────────────────────────────
    north_hand = state.hand_of(Seat.NORTH)
    if show_north_hand:
        # Show actual card symbols for North
        north_cards = " ".join(_card_symbol(c) for c in north_hand)
    else:
        north_cards = f"{_card_back_small()} " * min(len(north_hand), 4)
    north_label = _seat_label(Seat.NORTH, state)
    north_count = f"{light_gray_fg()}({len(north_hand)} cards){RESET}"
    if term_h > 40:
        lines.append("")
    lines.append(ansi_center(f"{north_label}  {north_cards}  {north_count}", term_w))

    # ── WEST | trick area | EAST  (3-column, same rows) ──────────────────────
    if term_h > 38:
        lines.append("")
    for row in _render_middle_section(state, term_w):
        lines.append(row)

    # ── DIVIDER ───────────────────────────────────────────────────────────────
    if term_h > 42:
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

    # Show persistent belote/rebelote badge derived from tracker (not the one-shot announced field)
    if state.belote_tracker[1]:
        from ..ansi import banner_bg, banner_fg

        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Rebelote! {RESET}"
    elif state.belote_tracker[0]:
        from ..ansi import banner_bg, banner_fg

        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Belote! {RESET}"

    lines.append(ansi_center(phase_info, term_w))
    if term_h > 44:
        lines.append("")

    # ── SOUTH hand ────────────────────────────────────────────────────────────
    south_hand = state.hand_of(Seat.SOUTH)
    south_legal = legal if state.turn == Seat.SOUTH else ()

    if south_hand:
        # Keyboard shortcut hints
        hints = " ".join(f"[{i + 1}]" for i in range(len(south_hand)))
        lines.append(ansi_center(hints, term_w))

        # Cards + cursor (already centered inside _render_hand_horizontal)
        for sl in _render_hand_horizontal(south_hand, selection, south_legal, term_w):
            lines.append(sl)

    south_label = _seat_label(Seat.SOUTH, state)
    lines.append(ansi_center(f"{south_label} (you)", term_w))

    # ── BIDDING PROMPT ────────────────────────────────────────────────────────
    if state.phase == Phase.BIDDING and state.turn == Seat.SOUTH:
        if term_h > 40:
            lines.append("")
        prompt = f"{BOLD}{gold_fg()}Bid: [P]ass  [1]♠  [2]♥  [3]♦  [4]♣{RESET}"
        lines.append(ansi_center(prompt, term_w))

    # Pad to terminal height to prevent screen flickering
    while len(lines) < term_h - 1:
        lines.append("")

    # CRITICAL: use \r\n not \n.
    rendered_lines = [line + clear_to_eol() for line in lines[:term_h]]
    return "".join([out, "\r\n".join(rendered_lines), show_cursor()])


def display_hud(state: GameState) -> None:
    """Targeted update of only the top HUD bar."""
    term_w, _ = get_term_size()
    sys.stdout.write(move(1, 1) + _build_hud(state, term_w))
    sys.stdout.flush()


def display(state: GameState, selection: int | None = None, show_north_hand: bool = False) -> None:
    sys.stdout.write(render(state, selection, show_north_hand))
    sys.stdout.flush()


def _calculate_base_row(term_h: int) -> int:
    """Calculate the base row for the trick mat mat dynamically."""
    base_row = 4  # HUD (1) + Divider (1) + North (1) + 1 (alignment)
    if term_h > 40:
        base_row += 1
    if term_h > 38:
        base_row += 1
    return base_row


def patch_trick_card(state: GameState, seat: Seat, card: Card) -> None:
    """Incrementally render a single card on the trick mat."""
    term_w, term_h = get_term_size()
    center_w = max(0, term_w - SIDE_COL_W * 2)

    # Coordinates (1-indexed for terminal)
    # Calculate base_row dynamically to match render() logic
    base_row = _calculate_base_row(term_h)

    # Vertical offsets from _render_trick_mat
    row_offsets = _TRICK_ROW_OFFSETS

    # Horizontal offsets
    w_start = max(0, center_w // 4 - CARD_W // 2)
    e_start = max(0, 3 * center_w // 4 - CARD_W // 2)
    n_s_start = (center_w - CARD_W) // 2

    col_offsets = {
        Seat.NORTH: n_s_start,
        Seat.WEST: w_start,
        Seat.EAST: e_start,
        Seat.SOUTH: n_s_start,
    }

    row = base_row + row_offsets[seat]
    col = SIDE_COL_W + col_offsets[seat] + 1

    face = _get_card_face(card)
    for i, line in enumerate(face):
        sys.stdout.write(move(row + i, col) + line)

    # Also update HUD if points changed
    sys.stdout.write(move(1, 1) + _build_hud(state, term_w))
    sys.stdout.flush()
