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
    banner_bg,
    banner_fg,
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
from ..ansi import (
    clear_screen as _clear_screen,
)
from ..context import TERMINAL
from ..deck import Card, Rank
from ..game import (
    GameState,
    Phase,
    Seat,
    legal_cards,
)
from ..themes import theme_manager
from .layout import STANDARD, LayoutPreset, choose_layout

# ── Backward-compat: the legacy module-level constants are now derived from the
# STANDARD preset for any code that still imports them directly. New rendering
# code receives a `layout: LayoutPreset` argument and reads dims from there.
CARD_W = STANDARD.card_w
CARD_H = STANDARD.card_h
CARD_GAP = STANDARD.card_gap
SIDE_COL_W = STANDARD.side_col_w


# Tracks the (term_w, term_h, layout.name) of the previous render so we can
# clear the screen when the layout flavour changes (avoids stale artifacts
# from a previous larger layout staying drawn under a now-compact one).
_LAST_RENDER_KEY: list[tuple[int, int, str] | None] = [None]


def _trick_row_offsets(layout: LayoutPreset) -> dict[Seat, int]:
    """Where each compass card lives inside the trick mat, given a layout.

    Mat layout (top-to-bottom):
      row 0: top pad (1)
      row 1: N label (1)
      rows 2 .. 2+CH-1: N card (CH rows)
      row 2+CH: gap (1)
      rows 2+CH+1 .. 2+2*CH: W/E cards (CH rows)
      row 2+2*CH+1: gap (1)
      rows 2+2*CH+2 .. 2+3*CH+1: S card (CH rows)
      row 3+3*CH+2: S label (1)
      row 3+3*CH+3: bottom pad (1)
    """
    ch = layout.card_h
    return {
        Seat.NORTH: 2,
        Seat.WEST: 2 + ch + 1,
        Seat.EAST: 2 + ch + 1,
        Seat.SOUTH: 2 + 2 * ch + 2,
    }


# Legacy constant retained for any caller still importing it (none in-tree now).
_TRICK_ROW_OFFSETS: Final = _trick_row_offsets(STANDARD)


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


@lru_cache(maxsize=2048)
def _card_face_internal(
    card: Card,
    selected: bool,
    legal: bool,
    theme_name: str,
    has_utf8: bool,
    card_w: int,
    card_h: int,
) -> list[str]:
    """Render a card as `card_h` lines of width `card_w` (cached).

    `card_h` must be ≥ 4 (top + at least one inner + corners + bottom).
    Standard layout (9×7) gets the full Art Nouveau face art; smaller layouts
    fall back to a minimal rank-corner-and-suit design that fits the tighter
    inner area.
    """
    rank_str = card.rank.value
    suit_sym = card.suit.symbol if has_utf8 else card.suit.name[0]

    # Top-left and bottom-right rank displays (always 2 visible cells, padded to
    # match "10" — the longest rank string).
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
    inner_w = card_w - 2

    # Ornate border characters
    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )

    def _line(content: str) -> str:
        return f"{prefix}{bg_code}{color}{b_v}{content}{b_v}{RESET}"

    top_border = f"{prefix}{bg_code}{color}{b_tl}{b_h * inner_w}{b_tr}{RESET}"
    bottom_border = f"{prefix}{bg_code}{color}{b_bl}{b_h * inner_w}{b_br}{RESET}"

    # Standard / spacious: room for 3-row centre art between the rank corners.
    # Compact (card_h <= 5): just rank corners and a single suit row.
    if card_h >= 7:
        art_top = " " * inner_w
        art_mid = " " * inner_w
        art_bot = " " * inner_w

        if card.rank == Rank.JACK:
            art_top = ("  ▄▆▄  " if has_utf8 else "  ***  ").center(inner_w)
            art_mid = f"  {suit_sym}V{suit_sym}  ".center(inner_w)
            art_bot = ("  ▀▆▀  " if has_utf8 else "  ***  ").center(inner_w)
        elif card.rank == Rank.QUEEN:
            art_top = ("  ╭▼╮  " if has_utf8 else "  ( )  ").center(inner_w)
            art_mid = f"  {suit_sym}Q{suit_sym}  ".center(inner_w)
            art_bot = ("  ╰─╯  " if has_utf8 else "  ---  ").center(inner_w)
        elif card.rank == Rank.KING:
            art_top = ("  ╔█╗  " if has_utf8 else "  [#]  ").center(inner_w)
            art_mid = f"  {suit_sym}K{suit_sym}  ".center(inner_w)
            art_bot = ("  ╚═╝  " if has_utf8 else "  [=]  ").center(inner_w)
        elif card.rank == Rank.ACE:
            art_top = ("   ▲   " if has_utf8 else "   ^   ").center(inner_w)
            art_mid = f"  {suit_sym}A{suit_sym}  ".center(inner_w)
            art_bot = ("   ▼   " if has_utf8 else "   v   ").center(inner_w)
        else:
            art_mid = f"   {suit_sym}   ".center(inner_w)

        # Truncate art rows to inner_w (handles card_w slightly different from 9).
        art_top = art_top[:inner_w].ljust(inner_w)
        art_mid = art_mid[:inner_w].ljust(inner_w)
        art_bot = art_bot[:inner_w].ljust(inner_w)

        rows = [
            top_border,
            _line(f"{tl_rank}{' ' * (inner_w - 2)}"),
            _line(art_top),
            _line(art_mid),
            _line(art_bot),
            _line(f"{' ' * (inner_w - 2)}{br_rank}"),
            bottom_border,
        ]
        # If a non-standard taller height was requested, add filler rows above
        # the bottom corner so total length == card_h.
        while len(rows) < card_h:
            rows.insert(-2, _line(" " * inner_w))
        return rows[:card_h]

    # Compact path (card_h == 5 typically): 3 inner rows, no Art Nouveau.
    # Layout: top-rank | suit/face indicator | bottom-rank.
    if is_face:
        center = f"{suit_sym}{rank_str}{suit_sym}".center(inner_w)
    else:
        center = suit_sym.center(inner_w)
    center = center[:inner_w].ljust(inner_w)

    rows = [
        top_border,
        _line(f"{tl_rank}{' ' * (inner_w - 2)}"),
        _line(center),
        _line(f"{' ' * (inner_w - 2)}{br_rank}"),
        bottom_border,
    ]
    while len(rows) < card_h:
        rows.insert(-2, _line(" " * inner_w))
    return rows[:card_h]


def _get_card_face(
    card: Card,
    selected: bool = False,
    legal: bool = True,
    layout: LayoutPreset = STANDARD,
) -> list[str]:
    """Helper to call cached _card_face with current global state."""
    return _card_face_internal(
        card,
        selected,
        legal,
        theme_manager._current_theme_name,
        TERMINAL.has_utf8,
        layout.card_w,
        layout.card_h,
    )


def clear_card_cache() -> None:
    """Clear the card face render cache. Call after changing the active theme."""
    _card_face_internal.cache_clear()


# Register callback to clear cache when theme changes
theme_manager.register_callback(clear_card_cache)


@lru_cache(maxsize=128)
def _card_back(theme_name: str, has_utf8: bool, card_w: int, card_h: int) -> list[str]:
    """Render a face-down card with an ornate pattern, sized to (card_w, card_h)."""
    inner_w = card_w - 2
    inner_h = card_h - 2  # rows between the borders

    # Decorative lattice pattern for the back, sized to inner_w
    fill = ("░▒▓▒░" if has_utf8 else "XXXXX")
    # Centre the fill in inner_w cells
    pattern_row = (" " + fill + " ").center(inner_w)[:inner_w].ljust(inner_w)

    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )

    res = [f"{card_back_bg()}{b_tl}{b_h * inner_w}{b_tr}{RESET}"]
    for _ in range(inner_h):
        res.append(f"{card_back_bg()}{b_v}{pattern_row}{b_v}{RESET}")
    res.append(f"{card_back_bg()}{b_bl}{b_h * inner_w}{b_br}{RESET}")
    return res


def _get_card_back(layout: LayoutPreset = STANDARD) -> list[str]:
    return _card_back(
        theme_manager._current_theme_name, TERMINAL.has_utf8, layout.card_w, layout.card_h
    )


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


def _felt_placeholder(layout: LayoutPreset = STANDARD) -> list[str]:
    """Card-sized dashed outline on the felt — shown for an empty trick slot."""
    inner_w = layout.card_w - 2
    dim = felt_placeholder_fg()
    top = felt_bg() + dim + "┌" + "─" * inner_w + "┐" + RESET
    mid = felt_bg() + dim + "│" + " " * inner_w + "│" + RESET
    bottom = felt_bg() + dim + "└" + "─" * inner_w + "┘" + RESET
    return [top] + [mid] * (layout.card_h - 2) + [bottom]


def _render_trick_mat(
    seat_map: dict[Seat, Card], center_w: int, layout: LayoutPreset = STANDARD
) -> list[str]:
    """Green felt mat with full card graphics at compass positions.

    Total height = 6 + 3*card_h rows (compact: 21, standard: 27, spacious: 33).
    """

    def slot(seat: Seat) -> list[str]:
        return (
            _get_card_face(seat_map[seat], layout=layout)
            if seat in seat_map
            else _felt_placeholder(layout)
        )

    n_card = slot(Seat.NORTH)
    w_card = slot(Seat.WEST)
    e_card = slot(Seat.EAST)
    s_card = slot(Seat.SOUTH)

    cw = layout.card_w
    ch = layout.card_h

    # Horizontal anchors: West centred at ¼, East centred at ¾ of center_w
    w_start = max(0, center_w // 4 - cw // 2)
    e_start = max(0, 3 * center_w // 4 - cw // 2)
    mid_gap = max(0, e_start - w_start - cw)
    r_pad = max(0, center_w - e_start - cw)

    n_label = _felt_pad(f"{light_gray_fg()}N{RESET}", center_w)
    s_label = _felt_pad(f"{light_gray_fg()}S{RESET}", center_w)

    rows: list[str] = []

    rows.append(_get_felt_blank(center_w))  # top padding
    rows.append(n_label)  # N label
    for line in n_card:  # North card (ch rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(_get_felt_blank(center_w))  # gap
    for i in range(ch):  # West + East (ch rows)
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
    for line in s_card:  # South card (ch rows)
        rows.append(_felt_pad(line, center_w))
    rows.append(s_label)  # S label
    rows.append(_get_felt_blank(center_w))  # bottom padding

    return rows  # 6 + 3*ch rows total


def _render_hand_horizontal(
    cards: tuple[Card, ...],
    selection: int | None,
    legal: tuple[Card, ...],
    term_w: int,
    layout: LayoutPreset = STANDARD,
) -> list[str]:
    """Render South's hand horizontally, already centered to term_w.

    The cursor ▲ row is offset to match the visual center of the selected card,
    accounting for the left-padding that ansi_center adds.
    """
    if not cards:
        return [""]

    # Build each card's card_h lines
    legal_set = set(legal)
    card_line_groups: list[list[str]] = [
        _get_card_face(c, selected=(i == selection), legal=(c in legal_set), layout=layout)
        for i, c in enumerate(cards)
    ]

    # Join cards horizontally with a layout.card_gap-space gap
    gap = " " * layout.card_gap
    slot_w = layout.card_w + len(gap)  # visible width of one card slot
    total_hand_w = len(cards) * slot_w - len(gap)  # visible width of full hand

    # Compute left padding that ansi_center will add — we need this for the cursor
    left_pad = max(0, (term_w - total_hand_w) // 2)

    rows: list[str] = []
    for row_idx in range(layout.card_h):
        raw = gap.join(group[row_idx] for group in card_line_groups)
        rows.append(ansi_center(raw, term_w))  # ← ANSI-aware centering

    # Cursor row — must account for the centering offset so ▲ lands under the card
    if selection is not None:
        cursor_col = left_pad + selection * slot_w + layout.card_w // 2
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


def _render_middle_section(
    state: GameState, term_w: int, layout: LayoutPreset = STANDARD
) -> list[str]:
    """Build the 3-column middle section: WEST | green felt mat | EAST."""
    west_hand = state.hand_of(Seat.WEST)
    east_hand = state.hand_of(Seat.EAST)

    side_col_w = layout.side_col_w
    center_w = max(0, term_w - side_col_w * 2)
    mat_height = 6 + 3 * layout.card_h

    # ── Center column (trick area / bidding up-card) ──────────────────────────
    center_rows = []
    if state.phase == Phase.BIDDING and state.up_card:
        # Show the up-card in the center
        up_face = _get_card_face(state.up_card, layout=layout)
        center_rows = [
            ansi_center(f"{light_gray_fg()}UP CARD{RESET}", 20),
            "",
        ]
        for row in up_face:
            center_rows.append(ansi_center(row, 20))
        center_rows.append("")

        # Pad to match trick mat height
        while len(center_rows) < mat_height:
            center_rows.insert(0, "")
            if len(center_rows) < mat_height:
                center_rows.append("")
    else:
        trick = state.current_trick
        seat_map: dict[Seat, Card] = {tc.seat: tc.card for tc in trick}
        center_rows = _render_trick_mat(seat_map, center_w, layout)

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

    # Last Trick Panel — hidden at compact widths (toggle with T/H key for full history).
    if state.completed_tricks and layout.show_last_trick_sidebar:
        last = state.completed_tricks[-1]
        right_rows[mid + 1] = f"{UNDERLINE}Last Trick:{RESET}"
        line1 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[:2])
        line2 = " ".join(f"{tc.seat.name[0]}:{_card_symbol(tc.card)}" for tc in last[2:])
        right_rows[mid + 2] = line1
        right_rows[mid + 3] = line2

    # ── Combine columns ───────────────────────────────────────────────────────
    result: list[str] = []
    for left, c, r in zip(left_rows, center_rows, right_rows, strict=False):
        result.append(ansi_ljust(left, side_col_w) + c + ansi_ljust(r, side_col_w))

    return result


def _build_hud(state: GameState, term_w: int, layout: LayoutPreset = STANDARD) -> str:
    """Build the top HUD bar, padded to term_w visible chars.

    Verbosity is layout-driven:
      - "verbose"  (spacious): all labels, help hints, theme name
      - "standard": current behaviour (full labels, hints, theme)
      - "compact"  (≤80 cols): abbreviated labels, no help hints, no theme name
    """
    if state.boss_modifiers.hide_hud:
        left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
        mid = f"{DIM} [HUD HIDDEN BY BOSS] {RESET}"
        if layout.hud_style == "compact":
            return ansi_ljust(left + "   " + mid, term_w)
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
    ns_pts, ew_pts = state.current_round_points

    left = f"{BOLD}{gold_fg()}BELOTE{RESET}"

    if layout.hud_style == "compact":
        # Abbreviated form: "BELOTE  T:♥  NS:200(+50)  EW:80(+30)  5/8  Tk:S"
        # Drops keyboard hints and theme name; both still reachable via H/help.
        taker_short = taker_name[0] if taker_name != "-" else "-"
        bar = (
            f"{left}  "
            f"{white_fg()}T:{trump_sym}  "
            f"NS:{BOLD}{ns}{RESET}{white_fg()}(+{ns_pts})  "
            f"EW:{BOLD}{ew}{RESET}{white_fg()}(+{ew_pts})  "
            f"{trick_num}/8  Tk:{taker_short}{RESET}"
        )
        return ansi_ljust(bar, term_w)

    # Standard / verbose: full labels, hints, theme on the right.
    theme_label = f"{DIM}Theme: {theme_manager.get_current().name}{RESET}"
    mid = (
        f"{white_fg()}Trump: {trump_sym}   "
        f"NS: {BOLD}{ns}{RESET}{white_fg()} (+{ns_pts})   "
        f"EW: {BOLD}{ew}{RESET}{white_fg()} (+{ew_pts})   "
        f"Trick {trick_num}/8   Taker: {taker_name}   "
        f"{DIM}[T]History [Z]Undo [S-T]Theme{RESET}"
    )
    bar = left + "   " + mid
    vlen_bar = visible_len(bar)
    vlen_theme = visible_len(theme_label)
    pad = max(0, term_w - vlen_bar - vlen_theme - 1)
    return bar + " " * pad + theme_label


def render(state: GameState, selection: int | None = None, show_north_hand: bool = False) -> str:
    """Pure: returns a full-screen ANSI-formatted string. No I/O.

    Terminal width is queried fresh on every call so resizing works correctly.
    The layout preset (compact / standard / spacious) is also picked fresh from
    the current dimensions, so resizing the terminal mid-game adapts on the
    next render.
    """
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)

    # If the size or layout flavour changed since the last render, prefix a
    # full screen clear so we don't leak artifacts from the previous layout.
    key = (term_w, term_h, layout.name)
    prefix_clear = ""
    if _LAST_RENDER_KEY[0] is not None and _LAST_RENDER_KEY[0] != key:
        prefix_clear = _clear_screen()
    _LAST_RENDER_KEY[0] = key

    out = prefix_clear + move(1, 1) + hide_cursor()
    legal: tuple[Card, ...] = ()
    if state.phase == Phase.PLAYING and state.turn == Seat.SOUTH:
        legal = legal_cards(state, Seat.SOUTH)

    lines: list[str] = []

    # ── HUD ──────────────────────────────────────────────────────────────────
    lines.append(_build_hud(state, term_w, layout))
    lines.append("─" * term_w)

    # ── NORTH ────────────────────────────────────────────────────────────────
    north_hand = state.hand_of(Seat.NORTH)
    if show_north_hand:
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
    for row in _render_middle_section(state, term_w, layout):
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

    if state.belote_tracker[1]:
        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Rebelote! {RESET}"
    elif state.belote_tracker[0]:
        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Belote! {RESET}"

    lines.append(ansi_center(phase_info, term_w))
    if term_h > 44:
        lines.append("")

    # ── SOUTH hand ────────────────────────────────────────────────────────────
    south_hand = state.hand_of(Seat.SOUTH)
    south_legal = legal if state.turn == Seat.SOUTH else ()

    if south_hand:
        hints = " ".join(f"[{i + 1}]" for i in range(len(south_hand)))
        lines.append(ansi_center(hints, term_w))

        for sl in _render_hand_horizontal(south_hand, selection, south_legal, term_w, layout):
            lines.append(sl)

    south_label = _seat_label(Seat.SOUTH, state)
    lines.append(ansi_center(f"{south_label} (you)", term_w))

    # ── BIDDING PROMPT ────────────────────────────────────────────────────────
    if state.phase == Phase.BIDDING and state.turn == Seat.SOUTH:
        if term_h > 40:
            lines.append("")
        prompt = f"{BOLD}{gold_fg()}Bid: [P]ass  [1]♠  [2]♥  [3]♦  [4]♣{RESET}"
        lines.append(ansi_center(prompt, term_w))

    # ── Vertical centering ──────────────────────────────────────────────────
    # If the terminal is taller than the rendered content, pad top + bottom so
    # the game centers vertically instead of clinging to the top.
    rendered_h = len(lines)
    if rendered_h < term_h - 1:
        slack = (term_h - 1) - rendered_h
        top_pad = slack // 2
        bottom_pad = slack - top_pad
        lines = [""] * top_pad + lines + [""] * bottom_pad

    # Only emit clear_to_eol on lines that actually have content; pure-padding
    # blank lines don't need it (we already cleared the screen on layout
    # changes and the previous render's content area was clear-to-eol'd).
    rendered_lines = [
        line + clear_to_eol() if line else line for line in lines[:term_h]
    ]
    return "".join([out, "\r\n".join(rendered_lines), show_cursor()])


def display_hud(state: GameState) -> None:
    """Targeted update of only the top HUD bar."""
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)
    sys.stdout.write(move(1, 1) + _build_hud(state, term_w, layout))
    sys.stdout.flush()


def display(state: GameState, selection: int | None = None, show_north_hand: bool = False) -> None:
    sys.stdout.write(render(state, selection, show_north_hand))
    sys.stdout.flush()


def _calculate_base_row(term_h: int, rendered_lines: int = 0) -> int:
    """Row at which the trick mat begins (1-indexed).

    Account for: HUD(1) + divider(1) + optional spacer + N row(1) + optional spacer.
    Then add any vertical-centering top-pad applied by render().
    """
    base_row = 4  # HUD + divider + N row + 1 (alignment under N row)
    if term_h > 40:
        base_row += 1  # spacer above N row
    if term_h > 38:
        base_row += 1  # spacer above middle section
    # If render() applied vertical centering, the top-pad shifts everything down.
    # `rendered_lines` is the unpadded total; if shorter than term_h-1 we add a
    # half-slack of empty rows above. Caller passes 0 for "I don't know" and we
    # skip the adjustment.
    if rendered_lines and rendered_lines < term_h - 1:
        slack = (term_h - 1) - rendered_lines
        base_row += slack // 2
    return base_row


def patch_trick_card(state: GameState, seat: Seat, card: Card) -> None:
    """Incrementally render a single card on the trick mat.

    Picks the active layout each call so a mid-game terminal resize re-routes
    coordinates correctly on the next patch.
    """
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)
    side_col_w = layout.side_col_w
    cw = layout.card_w
    center_w = max(0, term_w - side_col_w * 2)

    base_row = _calculate_base_row(term_h)

    row_offsets = _trick_row_offsets(layout)

    w_start = max(0, center_w // 4 - cw // 2)
    e_start = max(0, 3 * center_w // 4 - cw // 2)
    n_s_start = (center_w - cw) // 2

    col_offsets = {
        Seat.NORTH: n_s_start,
        Seat.WEST: w_start,
        Seat.EAST: e_start,
        Seat.SOUTH: n_s_start,
    }

    row = base_row + row_offsets[seat]
    col = side_col_w + col_offsets[seat] + 1

    face = _get_card_face(card, layout=layout)
    for i, line in enumerate(face):
        sys.stdout.write(move(row + i, col) + line)

    # Also update HUD if points changed
    sys.stdout.write(move(1, 1) + _build_hud(state, term_w, layout))
    sys.stdout.flush()
