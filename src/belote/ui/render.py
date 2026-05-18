from __future__ import annotations

import signal
import sys
from functools import lru_cache
from typing import Final

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
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
    felt_edge_bg,
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
from ..deck import Card, Rank, Suit
from ..game import (
    SANS_ATOUT_BID,
    GameState,
    Phase,
    Seat,
    legal_cards,
)
from ..themes import theme_manager
from .layout import STANDARD, LayoutPreset, choose_layout, vcenter_lines

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
_last_render_key: tuple[int, int, str] | None = None


# 3.9.3 (Phase 6): diff-based render. `_last_emitted_lines` holds the last
# `rendered_lines` (post-vcenter, with clear_to_eol per row) that `display()`
# committed to the terminal. `display()` diffs the next frame against it and
# emits only the rows that actually changed — same byte count for the first
# frame, near-zero for an idle re-render (e.g. polling for input between
# keystrokes). Set to None to force a full redraw (theme change, layout
# change, explicit `force=True`, env-var bypass).
#
# 4.1.0 — promoted to tuple[str, ...] | None. The list-of-strings form was
# rebuilt as a fresh list every frame; tuples are immutable and let callers
# treat the value as a reusable snapshot without a per-frame allocation.
_last_emitted_lines: tuple[str, ...] | None = None


# 4.1.0 (perf): cache `theme_manager.current_name` here so the felt-row
# segment cache key reads a module-local instead of a method call + dict
# lookup. Pattern mirrors `_active_palette` in `ansi.py`. Refreshed by the
# `_refresh_theme_name_cache` callback registered against the theme manager.
_cached_theme_name: str = theme_manager.current_name


def _refresh_theme_name_cache() -> None:
    global _cached_theme_name, _last_emitted_lines
    _cached_theme_name = theme_manager.current_name
    # Theme change invalidates the diff baseline so the next display() emits
    # a full frame with the new palette.
    _last_emitted_lines = None


theme_manager.register_callback(_refresh_theme_name_cache)


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

    # Both corners carry rank+suit (GRIMAUD-style index):
    #   top-left: "A♠" / "10♥" — 3 visible cells
    #   bottom-right mirror.
    if inner_w >= 3:
        tl_index = f"{rank_str.ljust(2)}{suit_sym}"
        br_index = f"{suit_sym}{rank_str.rjust(2)}"
        index_w = 3
    else:
        # Defensive fallback for impossibly-narrow layouts.
        tl_index = rank_str.ljust(2)
        br_index = rank_str.rjust(2)
        index_w = 2

    # Ornate border characters
    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )

    def _line(content: str) -> str:
        return f"{prefix}{bg_code}{color}{b_v}{content}{b_v}{RESET}"

    top_border = f"{prefix}{bg_code}{color}{b_tl}{b_h * inner_w}{b_tr}{RESET}"
    bottom_border = f"{prefix}{bg_code}{color}{b_bl}{b_h * inner_w}{b_br}{RESET}"

    # Standard / spacious: room for 3-row centre art between the index corners.
    # Compact (card_h <= 5): just index corners and a single suit row.
    if card_h >= 7:
        art_top = " " * inner_w
        art_mid = " " * inner_w
        art_bot = " " * inner_w

        if card.rank == Rank.JACK:
            # Knave with sword.
            art_top = ("╭━┳━╮" if has_utf8 else " ***  ").center(inner_w)
            art_mid = f"{suit_sym}J{suit_sym}".center(inner_w)
            art_bot = ("╰─┃─╯" if has_utf8 else " -|-  ").center(inner_w)
        elif card.rank == Rank.QUEEN:
            # Queen with jewelled headdress.
            art_top = ("╭◊─◊╮" if has_utf8 else " (-)  ").center(inner_w)
            art_mid = f"{suit_sym}Q{suit_sym}".center(inner_w)
            art_bot = ("╰─♥─╯" if has_utf8 else " -v-  ").center(inner_w)
        elif card.rank == Rank.KING:
            # King with crown.
            art_top = ("╭┻━┻╮" if has_utf8 else " /=\\  ").center(inner_w)
            art_mid = f"{suit_sym}K{suit_sym}".center(inner_w)
            art_bot = ("╰─┴─╯" if has_utf8 else " ---  ").center(inner_w)
        elif card.rank == Rank.ACE:
            # Ace: decorative wreath around the suit.
            art_top = ("╭─◆─╮" if has_utf8 else "*-+-*").center(inner_w)
            art_mid = f" {suit_sym}A{suit_sym} ".center(inner_w)
            art_bot = ("╰─◆─╯" if has_utf8 else "*-+-*").center(inner_w)
        else:
            # Pip cards (7-10): arrange suit pips in a recognisable pattern.
            pip = suit_sym if has_utf8 else card.suit.name[0]
            if card.rank == Rank.SEVEN:
                top_raw, mid_raw, bot_raw = (
                    f"{pip}   {pip}",
                    f"  {pip}  ",
                    f"{pip}   {pip}",
                )
            elif card.rank == Rank.EIGHT:
                top_raw, mid_raw, bot_raw = (
                    f"{pip}   {pip}",
                    f"{pip}   {pip}",
                    f"{pip}   {pip}",
                )
            elif card.rank == Rank.NINE:
                top_raw, mid_raw, bot_raw = (
                    f"{pip} {pip} {pip}",
                    f"{pip}   {pip}",
                    f"{pip} {pip} {pip}",
                )
            elif card.rank == Rank.TEN:
                top_raw, mid_raw, bot_raw = (
                    f"{pip} {pip} {pip}",
                    f"{pip} {pip} {pip}",
                    f"{pip}   {pip}",
                )
            else:
                top_raw = ""
                mid_raw = pip
                bot_raw = ""
            art_top = top_raw.center(inner_w)
            art_mid = mid_raw.center(inner_w)
            art_bot = bot_raw.center(inner_w)

        # Truncate art rows to inner_w (handles card_w slightly different from 9).
        art_top = art_top[:inner_w].ljust(inner_w)
        art_mid = art_mid[:inner_w].ljust(inner_w)
        art_bot = art_bot[:inner_w].ljust(inner_w)

        idx_pad = max(0, inner_w - index_w)
        rows = [
            top_border,
            _line(f"{tl_index}{' ' * idx_pad}"),
            _line(art_top),
            _line(art_mid),
            _line(art_bot),
            _line(f"{' ' * idx_pad}{br_index}"),
            bottom_border,
        ]
        # If a non-standard taller height was requested, add filler rows above
        # the bottom corner so total length == card_h.
        while len(rows) < card_h:
            rows.insert(-2, _line(" " * inner_w))
        return rows[:card_h]

    # Compact path (card_h == 5 typically): 3 inner rows, no Art Nouveau.
    # Layout: top-index | suit/face indicator | bottom-index.
    if is_face:
        center = f"{suit_sym}{rank_str}{suit_sym}".center(inner_w)
    else:
        center = suit_sym.center(inner_w)
    center = center[:inner_w].ljust(inner_w)

    idx_pad = max(0, inner_w - index_w)
    rows = [
        top_border,
        _line(f"{tl_index}{' ' * idx_pad}"),
        _line(center),
        _line(f"{' ' * idx_pad}{br_index}"),
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
        theme_manager.current_name,
        TERMINAL.has_utf8,
        layout.card_w,
        layout.card_h,
    )


def clear_card_cache() -> None:
    """Clear the card face render cache. Call after changing the active theme.

    3.9.3: also invalidates the render-diff baseline (Phase 6) so the next
    full render() emits every row — otherwise rows containing card faces
    would skip the diff and keep their old theme's escape sequences.

    3.9.4: also clears the felt-segment cache so the vignette + pip overlay
    pick up new theme colors on the next render.
    """
    _card_face_internal.cache_clear()
    _card_back.cache_clear()
    _felt_blank_internal.cache_clear()
    _felt_segment_cached.cache_clear()
    global _last_emitted_lines
    _last_emitted_lines = None


# Register callback to clear cache when theme changes
theme_manager.register_callback(clear_card_cache)


def invalidate_diff() -> None:
    """Reset the render-diff baseline.

    Overlay functions that write directly to stdout (bypassing `display()`)
    must call this before returning. Otherwise the next `display()` would
    diff the new game frame against the pre-overlay cached frame, conclude
    "no rows changed", and emit nothing — leaving the overlay visible
    behind a partial redraw.

    Cheaper than `clear_card_cache()` (no card-cache flush). Used by
    the `show_help` / `show_history` / `show_rules` overlays where the
    same diff-skip would otherwise apply.
    """
    global _last_emitted_lines
    _last_emitted_lines = None


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


def _card_back_small() -> str:
    """Single-line face-down card for opponent hand display."""
    char = "▓▓" if TERMINAL.has_utf8 else "[]"
    return f"{card_back_bg()}{char}{RESET}"


@lru_cache(maxsize=32)
def _felt_blank_internal(width: int, theme_name: str) -> str:
    return felt_bg() + " " * width + RESET


# 3.9.4 felt-mat polish ────────────────────────────────────────────────────
# Sparse braille texture stamped on blank felt cells. Pure function of
# (row_id, col) so the render-diff layer (display(), line ~956+) can still
# skip unchanged rows. Never random, never time-dependent.
_BRAILLE_DOTS: Final = "⠁⠂⠄⡀⠈⠐⠠⢀"
# Cells from each mat edge that use felt_edge_bg (vignette band).
_VIGNETTE_WIDTH: Final = 2


@lru_cache(maxsize=1024)
def _pip_at(row_id: int, col: int) -> str | None:
    # Pure deterministic function of (row_id, col). Called once per non-edge
    # felt cell on a cache-miss path of `_felt_segment_cached`; the lru_cache
    # collapses the second-and-later hits within a frame. UTF-8 fallback is
    # captured in `TERMINAL.has_utf8` which is process-constant, so the cache
    # entry is stable for the process lifetime. 4.1.0.
    if not TERMINAL.has_utf8:
        return None
    if ((row_id * 31 + col * 17) % 23) >= 2:
        return None
    return _BRAILLE_DOTS[(row_id * 7 + col * 13) % 8]


@lru_cache(maxsize=2048)
def _felt_segment_cached(
    width: int,
    row_id: int,
    col_offset: int,
    mat_w: int,
    theme_name: str,
    has_utf8: bool,
    top_or_bottom: bool,
) -> str:
    """`width` cells of felt starting at column [col_offset, col_offset+width).

    `mat_w` is the total mat width — used to decide which cells fall in the
    vignette band (leftmost / rightmost `_VIGNETTE_WIDTH` cols). On the top
    or bottom row of the mat, the entire row uses the edge color.
    """
    if width <= 0:
        return ""

    base = felt_bg()
    edge = felt_edge_bg()
    pip_fg = felt_placeholder_fg()

    parts: list[str] = []
    for i in range(width):
        col = col_offset + i
        is_edge_col = col < _VIGNETTE_WIDTH or col >= mat_w - _VIGNETTE_WIDTH
        is_edge = top_or_bottom or is_edge_col
        bg_seq = edge if is_edge else base
        glyph = None if is_edge else _pip_at(row_id, col)
        if glyph is not None:
            parts.append(pip_fg + bg_seq + glyph)
        else:
            parts.append(bg_seq + " ")
    parts.append(RESET)
    return "".join(parts)


def _felt_segment(
    width: int, row_id: int, col_offset: int, mat_w: int, *, top_or_bottom: bool = False
) -> str:
    # 4.1.0: read the cached theme name instead of querying the manager on
    # every felt-row call. The cache is refreshed by `_refresh_theme_name_cache`
    # registered against `theme_manager.register_callback` above.
    return _felt_segment_cached(
        width, row_id, col_offset, mat_w,
        _cached_theme_name, TERMINAL.has_utf8, top_or_bottom,
    )


def _felt_placeholder(layout: LayoutPreset = STANDARD) -> list[str]:
    """Card-sized dashed outline on the felt — shown for an empty trick slot."""
    inner_w = layout.card_w - 2
    dim = felt_placeholder_fg()
    top = felt_bg() + dim + "┌" + "─" * inner_w + "┐" + RESET
    mid = felt_bg() + dim + "│" + " " * inner_w + "│" + RESET
    bottom = felt_bg() + dim + "└" + "─" * inner_w + "┘" + RESET
    return [top] + [mid] * (layout.card_h - 2) + [bottom]


def _slot_anchors(center_w: int, cw: int) -> tuple[int, int, int]:
    """Horizontal column starts for the N/S, W, E slots inside the centre band."""
    n_s_start = max(0, (center_w - cw) // 2)
    w_start = max(0, center_w // 4 - cw // 2)
    e_start = max(0, 3 * center_w // 4 - cw // 2)
    return n_s_start, w_start, e_start


def _slot_frame_row(
    center_w: int,
    layout: LayoutPreset,
    segments: tuple[str, ...],
    *,
    row_id: int = 0,
    top_or_bottom: bool = False,
) -> str:
    """Build a felt row with `─` segments above/below the named slots.

    segments is a subset of {"N", "S", "W", "E"}; the corresponding slot
    columns receive a thin horizontal frame line in the felt-placeholder dim
    colour. All other cells use the felt segment (vignette + pip overlay).
    """
    cw = layout.card_w
    n_s_start, w_start, e_start = _slot_anchors(center_w, cw)
    h_char = "─" if TERMINAL.has_utf8 else "-"
    dim = felt_placeholder_fg()

    # Mark which columns are frame cells; the rest get felt-segment treatment.
    is_frame = [False] * center_w
    seg_starts = {"N": n_s_start, "S": n_s_start, "W": w_start, "E": e_start}
    for seg in segments:
        start = seg_starts[seg]
        for i in range(start, min(center_w, start + cw)):
            is_frame[i] = True

    out: list[str] = []
    i = 0
    while i < center_w:
        if is_frame[i]:
            j = i
            while j < center_w and is_frame[j]:
                j += 1
            out.append(felt_bg() + dim + h_char * (j - i) + RESET)
            i = j
        else:
            j = i
            while j < center_w and not is_frame[j]:
                j += 1
            out.append(_felt_segment(j - i, row_id, i, center_w, top_or_bottom=top_or_bottom))
            i = j
    return "".join(out)


def _felt_pad_ns(
    content: str, center_w: int, layout: LayoutPreset, *, row_id: int = 0
) -> str:
    """Centre a N/S card line on felt and inject │ borders one cell outside it."""
    cw = layout.card_w
    n_s_start, _, _ = _slot_anchors(center_w, cw)
    v = "│" if TERMINAL.has_utf8 else "|"
    dim = felt_placeholder_fg()

    has_left = n_s_start > 0
    right_total = max(0, center_w - n_s_start - cw)
    has_right = right_total > 0
    left_blank = max(0, n_s_start - 1)
    right_blank = max(0, right_total - 1)

    # Column offsets for the felt segments either side of the centred card.
    right_blank_start = n_s_start + cw + (1 if has_right else 0)

    parts: list[str] = []
    parts.append(_felt_segment(left_blank, row_id, 0, center_w))
    if has_left:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(content)
    if has_right:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(_felt_segment(right_blank, row_id, right_blank_start, center_w))
    return "".join(parts)


def _slot_label_ns(
    label_text: str, center_w: int, layout: LayoutPreset, *, row_id: int = 0
) -> str:
    """N/S compass label centred inside the slot, with │ slot borders."""
    cw = layout.card_w
    vlen = visible_len(label_text)
    pad = max(0, cw - vlen)
    lpad = pad // 2
    rpad = pad - lpad
    inner = felt_bg() + " " * lpad + RESET + label_text + felt_bg() + " " * rpad + RESET
    return _felt_pad_ns(inner, center_w, layout, row_id=row_id)


def _we_row(
    w_line: str, e_line: str, center_w: int, layout: LayoutPreset, *, row_id: int = 0
) -> str:
    """Build the W+E card row with │ borders flanking each card."""
    cw = layout.card_w
    _, w_start, e_start = _slot_anchors(center_w, cw)
    mid_gap = max(0, e_start - w_start - cw)
    r_pad = max(0, center_w - e_start - cw)
    v = "│" if TERMINAL.has_utf8 else "|"
    dim = felt_placeholder_fg()

    has_w_left = w_start > 0
    has_w_right_and_e_left = mid_gap >= 2
    has_e_right = r_pad > 0

    w_left_blank = max(0, w_start - 1)
    mid_blank = max(0, mid_gap - (2 if has_w_right_and_e_left else 0))
    e_right_blank = max(0, r_pad - 1)

    # Column offsets for the inter-card felt segments.
    mid_blank_start = w_start + cw + (1 if has_w_right_and_e_left else 0)
    e_right_blank_start = e_start + cw + (1 if has_e_right else 0)

    parts: list[str] = []
    parts.append(_felt_segment(w_left_blank, row_id, 0, center_w))
    if has_w_left:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(w_line)
    if has_w_right_and_e_left:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(_felt_segment(mid_blank, row_id, mid_blank_start, center_w))
    if has_w_right_and_e_left:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(e_line)
    if has_e_right:
        parts.append(felt_bg() + dim + v + RESET)
    parts.append(_felt_segment(e_right_blank, row_id, e_right_blank_start, center_w))
    return "".join(parts)


def _render_trick_mat(
    seat_map: dict[Seat, Card], center_w: int, layout: LayoutPreset = STANDARD
) -> list[str]:
    """Felt mat with full card graphics at compass positions.

    Total height = 6 + 3*card_h rows (compact: 21, standard: 27, spacious: 33).
    Each slot is wrapped by a thin frame drawn in the felt-placeholder colour
    on the cells immediately surrounding the card area, so a played card
    always reads as anchored within its player's slot. Blank felt cells carry
    a deterministic braille pip overlay and a left/right vignette band.
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

    ch = layout.card_h
    mat_h = 6 + 3 * ch  # total mat height — needed for top/bottom row markers

    rows: list[str] = []

    def row_id() -> int:
        # The pip overlay is a pure function of (row_id, col); using the
        # current row index keeps the pattern stable across re-renders so the
        # display() diff layer can still skip unchanged rows.
        return len(rows)

    def is_top_or_bottom() -> bool:
        return len(rows) == 0 or len(rows) == mat_h - 1

    rows.append(_slot_frame_row(
        center_w, layout, ("N",), row_id=row_id(), top_or_bottom=is_top_or_bottom()
    ))
    rows.append(_slot_label_ns(f"{light_gray_fg()}N{RESET}", center_w, layout, row_id=row_id()))
    for line in n_card:
        rows.append(_felt_pad_ns(line, center_w, layout, row_id=row_id()))
    rows.append(_slot_frame_row(center_w, layout, ("N", "W", "E"), row_id=row_id()))
    for i in range(ch):
        rows.append(_we_row(w_card[i], e_card[i], center_w, layout, row_id=row_id()))
    rows.append(_slot_frame_row(center_w, layout, ("W", "E", "S"), row_id=row_id()))
    for line in s_card:
        rows.append(_felt_pad_ns(line, center_w, layout, row_id=row_id()))
    rows.append(_slot_label_ns(f"{light_gray_fg()}S{RESET}", center_w, layout, row_id=row_id()))
    rows.append(_slot_frame_row(
        center_w, layout, ("S",), row_id=row_id(), top_or_bottom=is_top_or_bottom()
    ))

    return rows  # 6 + 3*ch rows total


# Decorative outer frame for the trick mat (STANDARD / SPACIOUS only).
# COMPACT (80×32) has no row budget for the extra wrapper.
def _render_trick_mat_framed(
    seat_map: dict[Seat, Card], center_w: int, layout: LayoutPreset
) -> list[str]:
    """Wrap _render_trick_mat with a 1-cell decorative border + corner glyphs.

    Reserves 2 columns (left + right border) and 2 rows (top + bottom border).
    The inner mat is drawn at width center_w - 2.
    """
    if center_w < 8 or not TERMINAL.has_utf8:
        return _render_trick_mat(seat_map, center_w, layout)

    inner_w = center_w - 2
    inner = _render_trick_mat(seat_map, inner_w, layout)

    dim = felt_placeholder_fg()
    edge = felt_edge_bg()
    tl, tr, bl, br, h, v, corner = "╔", "╗", "╚", "╝", "═", "║", "◆"

    # Place corner ornaments at ~⅓ and ⅔ of the top/bottom borders.
    a1 = max(1, inner_w // 3)
    a2 = max(a1 + 1, (2 * inner_w) // 3)

    def horizontal(left: str, right: str) -> str:
        chars = [h] * inner_w
        if a1 < inner_w:
            chars[a1] = corner
        if a2 < inner_w:
            chars[a2] = corner
        return edge + dim + left + "".join(chars) + right + RESET

    top = horizontal(tl, tr)
    bot = horizontal(bl, br)
    side = edge + dim + v + RESET

    return [top] + [side + row + side for row in inner] + [bot]


def _render_hand_horizontal(
    cards: tuple[Card, ...],
    selection: int | None,
    legal: tuple[Card, ...],
    term_w: int,
    layout: LayoutPreset = STANDARD,
    trump: Suit | None = None,
    show_readout: bool = True,
) -> list[str]:
    """Render South's hand horizontally, already centered to term_w.

    Below the cards we add:
      - a `card_w`-wide highlight bar in highlight_bg under the selected card
        (replaces the bare ▲ cursor; clearer on busy felt backgrounds);
      - if `show_readout` (only when the terminal has row slack), a centered
        card-name readout like `► A♠ — Trump ◄`, color-coded by suit / trump
        / legality. Suppressed at min layout sizes to preserve room for the
        south hand at the bottom of the screen.
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

    if selection is not None and 0 <= selection < len(cards):
        # Highlight bar — `card_w` cells in highlight_bg directly under the
        # selected card. ANSI-positioned via leading spaces; no escape pollution
        # past the bar because we RESET at the end.
        bar_col = left_pad + selection * slot_w
        rows.append(" " * bar_col + highlight_bg() + " " * layout.card_w + RESET)

        if show_readout:
            card = cards[selection]
            is_trump = trump is not None and (
                card.suit == trump or trump == Suit.TOUT_ATOUT
            )
            is_legal = card in legal_set
            suit_color = (
                gold_fg() if is_trump
                else (red_fg() if card.suit.is_red else white_fg())
            )
            if not is_legal:
                suit_color = light_gray_fg()
            tag = " — Trump" if is_trump else ("" if is_legal else " — Illegal")
            label = (
                f"{suit_color}► {BOLD}{card.rank.value}{card.suit.symbol}{RESET}"
                f"{suit_color}{tag} ◄{RESET}"
            )
            rows.append(ansi_center(label, term_w))

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
        # Decorative frame costs +2 rows. Only fire when the terminal has at
        # least 2 rows of slack over the chosen layout's minimum — otherwise
        # vcenter would truncate the bottom of the screen.
        _, term_h = get_term_size()
        if term_h >= layout.min_rows + 2:
            center_rows = _render_trick_mat_framed(seat_map, center_w, layout)
        else:
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

    # Last Trick Panel — hidden at compact widths (press H for full history).
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
        f"{DIM}[H]Hist [T]Theme [Z]Undo [I]HUD{RESET}"
    )
    bar = left + "   " + mid
    vlen_bar = visible_len(bar)
    vlen_theme = visible_len(theme_label)
    pad = max(0, term_w - vlen_bar - vlen_theme - 1)
    return bar + " " * pad + theme_label


def _build_bid_prompt_lines(state: GameState, term_w: int, bid_selection: int) -> list[str]:
    """Build the in-frame bidding prompt: optional tendency line, then the
    selector (Round 1: inline highlighted Take/Pass; Round 2: boxed grid).

    Painted as part of the main render so no writes happen after `display()` —
    that's what was causing the Konsole UI to stack (post-render \\r\\n's
    scrolled the alt-screen, leaving stale content on rows the next frame's
    blank padding doesn't repaint).
    """
    if state.bidding_round == 1:
        up_card = state.up_card
        assert up_card is not None  # guaranteed by Phase.BIDDING + round 1
        labels = [f"Take {up_card.suit.symbol}", "Pass"]
    else:
        all_suits = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
        up_card = state.up_card
        assert up_card is not None
        other_suits = [s for s in all_suits if s != up_card.suit]
        labels = [s.symbol for s in other_suits] + ["TA", "SA", "Pass"]
        round2_suits: list[Suit | str | None] = [
            *other_suits,
            Suit.TOUT_ATOUT,
            SANS_ATOUT_BID,
            None,
        ]

    lines: list[str] = []

    tendency = state._joker_state.get("partner_bid_tendency_text")
    if isinstance(tendency, str) and tendency:
        lines.append(ansi_center(f"{DIM}{tendency}{RESET}", term_w))

    if state.bidding_round == 2:
        inner_w = 60
        opt_str = ""
        for i, lbl in enumerate(labels):
            prefix = f"{BOLD}{gold_fg()}" if i == bid_selection else ""
            color = ""
            opt = round2_suits[i]
            if isinstance(opt, Suit):
                color = red_fg() if opt.is_red else black_fg()
            entry = f"{prefix}({i + 1}) {color}{lbl}{RESET}{prefix}"
            entry = f"{REVERSE} {entry} {RESET}" if i == bid_selection else f" {entry} "
            opt_str += entry + "  "

        box = [
            f"┌{'─' * inner_w}┐",
            f"│{f'ROUND {state.bidding_round} BID'.center(inner_w)}│",
            f"├{'─' * inner_w}┤",
            f"│{' ' * inner_w}│",
            f"│{ansi_center(opt_str.strip(), inner_w)}│",
            f"│{' ' * inner_w}│",
            f"└{'─' * inner_w}┘",
        ]
        lines.extend(ansi_center(bl, term_w) for bl in box)
    else:
        parts = [
            f"{BOLD}{gold_fg()}({i + 1}){lbl}{RESET}" if i == bid_selection else f"({i + 1}){lbl}"
            for i, lbl in enumerate(labels)
        ]
        prompt = f"{BOLD}{white_fg()}Round {state.bidding_round} Bid: {'  '.join(parts)}{RESET}"
        lines.append(ansi_center(prompt, term_w))

    return lines


def render(
    state: GameState,
    selection: int | None = None,
    show_north_hand: bool = False,
    bid_selection: int | None = None,
) -> str:
    """Pure: returns a full-screen ANSI-formatted string. No I/O.

    Terminal width is queried fresh on every call so resizing works correctly.
    The layout preset (compact / standard / spacious) is also picked fresh from
    the current dimensions, so resizing the terminal mid-game adapts on the
    next render.

    `bid_selection` paints the bidding selector with the highlighted option
    inside the frame. Pass `None` for non-interactive renders (the simple
    static "Bid: [P]ass [1]♠..." hint shows instead).
    """
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)

    # If the size or layout flavour changed since the last render, prefix a
    # full screen clear so we don't leak artifacts from the previous layout.
    # 3.9.3 (Phase 6): also invalidate the diff baseline so display() falls
    # back to a full emit — the diff would otherwise compare against rows
    # painted under the old layout.
    global _last_render_key, _last_emitted_lines
    key = (term_w, term_h, layout.name)
    prefix_clear = ""
    if _last_render_key is not None and _last_render_key != key:
        prefix_clear = _clear_screen()
        _last_emitted_lines = None
    _last_render_key = key

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

        # Readout adds +1 row; suppress at layout minimum to avoid pushing the
        # south hand off the bottom. Threshold matches the +1-spacer pattern
        # used elsewhere in render().
        show_readout = term_h > layout.min_rows
        for sl in _render_hand_horizontal(
            south_hand, selection, south_legal, term_w, layout,
            trump=state.trump, show_readout=show_readout,
        ):
            lines.append(sl)

    south_label = _seat_label(Seat.SOUTH, state)
    lines.append(ansi_center(f"{south_label} (you)", term_w))

    # ── BIDDING PROMPT ────────────────────────────────────────────────────────
    if state.phase == Phase.BIDDING and state.turn == Seat.SOUTH:
        if term_h > 40:
            lines.append("")
        if bid_selection is not None:
            lines.extend(_build_bid_prompt_lines(state, term_w, bid_selection))
        else:
            prompt = f"{BOLD}{gold_fg()}Bid: [P]ass  [1]♠  [2]♥  [3]♦  [4]♣{RESET}"
            lines.append(ansi_center(prompt, term_w))

    # ── Vertical centering ──────────────────────────────────────────────────
    # If the terminal is taller than the rendered content, pad top + bottom so
    # the game centers vertically instead of clinging to the top.
    rendered_h = len(lines)
    # Cache the unpadded line count so patch_trick_card() — which writes single
    # cards into the trick mat after render() — can compute the same vertical-
    # centering offset render() applied. Pre-3.2 it passed 0 (the "I don't
    # know" sentinel) and skipped the offset entirely, drawing rows too high
    # on tall terminals (>40 rows).
    global _last_rendered_unpadded_h
    _last_rendered_unpadded_h = rendered_h
    lines = vcenter_lines(lines, term_h)

    # Always emit clear_to_eol on every row, including blank padding. Konsole
    # (and other strict emulators) don't auto-blank cells when an empty string
    # passes through, so any debris from external writes (announcements, etc.)
    # would remain visible. The cost is one extra 3-byte escape per row.
    rendered_lines: tuple[str, ...] = tuple(
        line + clear_to_eol() for line in lines[:term_h]
    )
    # 3.9.3 Phase 6: stash the per-row tuple so display() can diff against the
    # previous frame and skip emitting unchanged rows. Layout changes are
    # already reflected via `prefix_clear` above + the cache invalidation in
    # display(); theme changes invalidate via the theme_manager callback.
    # 4.1.0: switched from list to tuple — the side-channel is read-only by
    # design and tuples avoid the per-frame list allocation.
    global _pending_rendered_lines
    _pending_rendered_lines = rendered_lines
    return "".join([out, "\r\n".join(rendered_lines), show_cursor()])


# 3.9.3 Phase 6: side channel from render() → display(). Holds the line tuple
# from the most recent render() call so display() can diff without re-rendering.
# 4.1.0: typed as tuple — see render() for the rationale.
_pending_rendered_lines: tuple[str, ...] | None = None


# Set by render() so patch_trick_card() can re-apply the same vertical-
# centering offset. 0 means "render() hasn't run yet" — _calculate_base_row
# treats that as the no-adjustment fallback.
_last_rendered_unpadded_h: int = 0


def display_hud(state: GameState) -> None:
    """Targeted update of only the top HUD bar."""
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)
    sys.stdout.write(move(1, 1) + _build_hud(state, term_w, layout))
    sys.stdout.flush()


def display(
    state: GameState,
    selection: int | None = None,
    show_north_hand: bool = False,
    bid_selection: int | None = None,
    force: bool = False,
) -> None:
    """Emit the rendered frame to stdout.

    3.9.3 (Phase 6) — diff-based emit. When `_last_emitted_lines` is set
    and we're not forced into a full redraw, only rows that actually
    changed are written. The terminal's prior contents on unchanged rows
    are reused, so an idle re-render (e.g. polling input between
    keystrokes) reduces from ~28 row writes to zero.

    Bypass via:
    * `force=True` — caller knows the screen is dirty (post-clear, after
      menu/scene transition, on layout boundaries).
    * env var `BELOTE_NO_DIFF=1` — escape hatch for debugging artifact
      complaints. Mirrors the existing `NO_COLOR` style.

    Layout/theme changes invalidate the baseline automatically (render()
    + the theme_manager callback both set `_last_emitted_lines = None`).
    """
    import os as _os

    # 4.1.0 (C6): pre-clear the side-channel so an exception escaping render()
    # can't leave a stale tuple for a later display() call to diff against.
    global _pending_rendered_lines, _last_emitted_lines
    _pending_rendered_lines = None

    full_str = render(state, selection, show_north_hand, bid_selection=bid_selection)

    use_diff = (
        not force
        and _last_emitted_lines is not None
        and _pending_rendered_lines is not None
        and len(_pending_rendered_lines) == len(_last_emitted_lines)
        and _os.environ.get("BELOTE_NO_DIFF") != "1"
    )

    if not use_diff:
        sys.stdout.write(full_str)
        sys.stdout.flush()
        _last_emitted_lines = _pending_rendered_lines or ()
        return

    # Diff path — _pending_rendered_lines was populated by render() above.
    assert _pending_rendered_lines is not None
    new_lines = _pending_rendered_lines
    old_lines = _last_emitted_lines
    assert old_lines is not None
    parts: list[str] = [hide_cursor()]
    for row_idx, (new_line, old_line) in enumerate(zip(new_lines, old_lines, strict=True)):
        if new_line != old_line:
            # Rows are 1-indexed in ANSI. Always prefix RESET so a stale
            # color SGR from the previous row can't bleed into this one.
            # 4.1.0 (C4): append clear_to_eol so a row that shrunk (e.g.
            # terminal narrowed mid-game) doesn't leave stale chars past
            # the new line's end. Full-render rows already include this
            # via the render() loop above; the diff path missed it pre-4.1.0.
            parts.append(move(row_idx + 1, 1) + RESET + new_line + clear_to_eol())
    parts.append(show_cursor())
    sys.stdout.write("".join(parts))
    sys.stdout.flush()
    _last_emitted_lines = new_lines


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


def patch_trick_card(
    state: GameState, seat: Seat, card: Card, *, force_hud: bool = False
) -> None:
    """Incrementally render a single card on the trick mat.

    Picks the active layout each call so a mid-game terminal resize re-routes
    coordinates correctly on the next patch.

    The HUD bar at row 1 is only rebuilt when ``force_hud=True``. By default
    the HUD is left as-is: ``_build_hud`` reads ``state.current_round_points``
    and ``state.team_scores``, neither of which change between
    ``patch_trick_card`` calls within a single trick (the running totals
    only advance when ``play_card`` commits the completed trick, which the
    caller then re-renders via ``display()``). Pre-3.8.0 the HUD was rebuilt
    on every card play — ~300 µs of wasted work per round.
    """
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)
    side_col_w = layout.side_col_w
    cw = layout.card_w
    center_w = max(0, term_w - side_col_w * 2)

    base_row = _calculate_base_row(term_h, _last_rendered_unpadded_h)

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

    # Build the whole patch as a single string and emit one stdout.write so
    # signal-interruptible terminals (Konsole especially) can't paint half the
    # card before the HUD update lands. Pre-3.5.0 each card-face line + the HUD
    # update were separate writes, which produced torn frames under load.
    face = _get_card_face(card, layout=layout)
    # NOTE: do NOT append clear_to_eol() per row. The card frame is positioned
    # at a specific column over the felt mat, not at end-of-line; clear_to_eol
    # would wipe felt-coloured cells to the right of every face line with the
    # terminal's default (black) background, leaving visible grey/black bars
    # next to every patched card. (Regression caught visually in 4.6.2 and
    # reverted.) Row-shrink debris on terminal resize is handled by the
    # invalidate_diff() call below — the next full display() repaints the row.
    buf = [move(row + i, col) + line for i, line in enumerate(face)]
    if force_hud:
        buf.append(move(1, 1) + _build_hud(state, term_w, layout))
    sys.stdout.write("".join(buf))
    sys.stdout.flush()

    # 4.0.1: invalidate the render-diff baseline. patch_trick_card writes a
    # card directly to the terminal, bypassing display(). Without this call,
    # `_last_emitted_lines` keeps reflecting the pre-patch frame. When the
    # next trick starts and display() runs, the diff compares the new
    # "empty mat" frame against the cached "empty mat" baseline, sees no
    # changes, and emits nothing — leaving the patched cards from the
    # previous trick visible. User-visible symptom: leftover card fragments
    # at non-lead seats when a new trick begins. Same architectural rule
    # as the 4.0.0 popup fix: any write that bypasses display() must
    # invalidate the diff baseline.
    invalidate_diff()
