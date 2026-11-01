"""The classic table: felt mat, trick slots, hands and the middle section.

Split out of `ui/render.py` in 4.11.0. Felt cells are pure functions of
(row, col, theme) so the diff renderer in `render.py` can skip unchanged rows.
The names stay importable from `belote.ui.render` for compatibility.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from ..ansi import (
    BOLD,
    RESET,
    UNDERLINE,
    ansi_center,
    ansi_ljust,
    felt_bg,
    felt_edge_bg,
    felt_placeholder_fg,
    gold_fg,
    highlight_bg,
    light_gray_fg,
    palette,
    red_fg,
    visible_len,
    white_fg,
)
from ..context import TERMINAL
from ..cosmetics import TableFrame
from ..deck import Card, Suit
from ..game import (
    GameState,
    Phase,
    Seat,
    legal_cards,
)
from . import cards as _cards
from .cards import (
    _card_back_small,
    _card_symbol,
    _get_card_face,
    card_back_lines,
)
from .layout import STANDARD, LayoutPreset


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


@lru_cache(maxsize=32)
def _felt_blank_internal(width: int, theme_name: str) -> str:  # noqa: ARG001 — cache key
    return felt_bg() + " " * width + RESET


# 3.9.4 felt-mat polish ────────────────────────────────────────────────────
# Sparse braille texture stamped on blank felt cells. Pure function of
# (row_id, col) so the render-diff layer (display(), line ~956+) can still
# skip unchanged rows. Never random, never time-dependent.
_BRAILLE_DOTS: Final = "⠁⠂⠄⡀⠈⠐⠠⢀"
# Cells from each mat edge that use felt_edge_bg (vignette band).
_VIGNETTE_WIDTH: Final = 2


@lru_cache(maxsize=8192)
def _pip_at(row_id: int, col: int) -> str | None:
    # Pure deterministic function of (row_id, col). Called once per non-edge
    # felt cell on a cache-miss path of `_felt_segment_cached`; the lru_cache
    # collapses the second-and-later hits within a frame. UTF-8 fallback is
    # captured in `TERMINAL.has_utf8` which is process-constant, so the cache
    # entry is stable for the process lifetime. 4.1.0.
    # 4.9.5 (P1): bumped 4096→8192 — a spacious-layout mat (term_w ≥ 120) can
    # need >5000 distinct (row_id, col) keys per frame, which thrashed the
    # 4096 cache and recomputed ~1000 cells every frame.
    if not TERMINAL.has_utf8:
        return None
    if ((row_id * 31 + col * 17) % 23) >= 2:
        return None
    return _BRAILLE_DOTS[(row_id * 7 + col * 13) % 8]


@lru_cache(maxsize=4096)
def _felt_segment_cached(
    width: int,
    row_id: int,
    col_offset: int,
    mat_w: int,
    theme_name: str,  # noqa: ARG001 — lru_cache key: per-theme colors
    has_utf8: bool,  # noqa: ARG001 — lru_cache key: glyph set
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
    # registered in `ui/cards.py`.
    return _felt_segment_cached(
        width,
        row_id,
        col_offset,
        mat_w,
        _cards._cached_theme_name,
        TERMINAL.has_utf8,
        top_or_bottom,
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


def _felt_pad_ns(content: str, center_w: int, layout: LayoutPreset, *, row_id: int = 0) -> str:
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


def _slot_label_ns(label_text: str, center_w: int, layout: LayoutPreset, *, row_id: int = 0) -> str:
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


def masked_seats(state: GameState) -> frozenset[Seat]:
    """Seats whose card on the mat is drawn face-down (Le Bal Masqué: the
    opponents, while the first trick is still open)."""
    if state.variants.masked_first_trick and not state.completed_tricks:
        return frozenset({Seat.EAST, Seat.WEST})
    return frozenset()


def _render_trick_mat(
    seat_map: dict[Seat, Card],
    center_w: int,
    layout: LayoutPreset = STANDARD,
    *,
    labels: bool = True,
    masked: frozenset[Seat] = frozenset(),
) -> list[str]:
    """Felt mat with full card graphics at compass positions.

    Total height = 6 + 3*card_h rows (compact: 21, standard: 27, spacious: 33).
    Each slot is wrapped by a thin frame drawn in the felt-placeholder colour
    on the cells immediately surrounding the card area, so a played card
    always reads as anchored within its player's slot. Blank felt cells carry
    a deterministic braille pip overlay and a left/right vignette band.
    """

    def slot(seat: Seat) -> list[str]:
        if seat not in seat_map:
            return _felt_placeholder(layout)
        if seat in masked:
            return card_back_lines(layout)
        return _get_card_face(seat_map[seat], layout=layout)

    n_card = slot(Seat.NORTH)
    w_card = slot(Seat.WEST)
    e_card = slot(Seat.EAST)
    s_card = slot(Seat.SOUTH)

    ch = layout.card_h
    # Total mat height — needed for top/bottom row markers. 4.11.0: without
    # the "N"/"S" label rows (tight terminals) it is 4 + 3*ch.
    mat_h = (6 if labels else 4) + 3 * ch

    rows: list[str] = []

    def row_id() -> int:
        # The pip overlay is a pure function of (row_id, col); using the
        # current row index keeps the pattern stable across re-renders so the
        # display() diff layer can still skip unchanged rows.
        return len(rows)

    def is_top_or_bottom() -> bool:
        return len(rows) == 0 or len(rows) == mat_h - 1

    rows.append(
        _slot_frame_row(center_w, layout, ("N",), row_id=row_id(), top_or_bottom=is_top_or_bottom())
    )
    if labels:
        rows.append(_slot_label_ns(f"{light_gray_fg()}N{RESET}", center_w, layout, row_id=row_id()))
    for line in n_card:
        rows.append(_felt_pad_ns(line, center_w, layout, row_id=row_id()))
    rows.append(_slot_frame_row(center_w, layout, ("N", "W", "E"), row_id=row_id()))
    for i in range(ch):
        rows.append(_we_row(w_card[i], e_card[i], center_w, layout, row_id=row_id()))
    rows.append(_slot_frame_row(center_w, layout, ("W", "E", "S"), row_id=row_id()))
    for line in s_card:
        rows.append(_felt_pad_ns(line, center_w, layout, row_id=row_id()))
    if labels:
        rows.append(_slot_label_ns(f"{light_gray_fg()}S{RESET}", center_w, layout, row_id=row_id()))
    rows.append(
        _slot_frame_row(center_w, layout, ("S",), row_id=row_id(), top_or_bottom=is_top_or_bottom())
    )

    return rows  # mat_h rows total


def frame_rows(frame: TableFrame, inner: list[str], inner_w: int) -> list[str] | None:
    """Wrap `inner` rows (each `inner_w` cells wide) in `frame`'s 1-cell
    border, or None when the frame has no glyphs for this terminal (Art
    Nouveau draws nothing without UTF-8, as before 4.11.0)."""
    g = frame.glyphs if TERMINAL.has_utf8 else frame.glyphs_ascii
    if g is None:
        return None
    color = palette(frame.fg) + (BOLD if frame.bold else "")
    edge = felt_edge_bg()
    marks = [inner_w * n // d for n, d in frame.ornaments]

    def horizontal(left: str, right: str) -> str:
        chars = [g.h] * inner_w
        for a in marks:
            if 0 <= a < inner_w:
                chars[a] = g.ornament
        return edge + color + left + "".join(chars) + right + RESET

    side = edge + color + g.v + RESET
    return (
        [horizontal(g.tl, g.tr)] + [side + row + side for row in inner] + [horizontal(g.bl, g.br)]
    )


def mat_is_framed(center_w: int) -> bool:
    """Whether `_render_trick_mat_framed` actually draws a border here (the
    frame needs room across and glyphs for this terminal)."""
    frame = _cards._cached_frame
    return center_w >= 8 and not (frame.glyphs_ascii is None and not TERMINAL.has_utf8)


# Decorative outer frame for the trick mat; whether there are rows for it is
# decided by `layout.fit_table` (4.11.0).
def _render_trick_mat_framed(
    seat_map: dict[Seat, Card],
    center_w: int,
    layout: LayoutPreset,
    *,
    labels: bool = True,
    masked: frozenset[Seat] = frozenset(),
) -> list[str]:
    """Wrap _render_trick_mat with a 1-cell decorative border + corner glyphs.

    Reserves 2 columns (left + right border) and 2 rows (top + bottom border).
    The inner mat is drawn at width center_w - 2. 4.11.0: the border style is
    the player's table frame (`cosmetics.TABLE_FRAMES`, default Art Nouveau).
    """
    frame = _cards._cached_frame
    if not mat_is_framed(center_w):
        return _render_trick_mat(seat_map, center_w, layout, labels=labels, masked=masked)

    inner_w = center_w - 2
    inner = _render_trick_mat(seat_map, inner_w, layout, labels=labels, masked=masked)
    framed = frame_rows(frame, inner, inner_w)
    assert framed is not None  # glyph availability checked above
    return framed


def frame_preview(frame: TableFrame, width: int, height: int) -> list[str]:
    """A `width` x `height` felt swatch wrapped in `frame` (Settings preview).
    Without glyphs for this terminal the bare swatch is returned."""
    inner_w, inner_h = max(1, width - 2), max(1, height - 2)
    inner = [_felt_segment(inner_w, r + 1, 1, inner_w + 2) for r in range(inner_h)]
    return frame_rows(frame, inner, inner_w) or inner


def _render_hand_horizontal(
    cards: tuple[Card, ...],
    selection: int | None,
    legal: tuple[Card, ...],
    term_w: int,
    layout: LayoutPreset = STANDARD,
    trump: Suit | None = None,
    show_readout: bool = True,
    show_bar: bool = True,
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

    # 4.9.0 / U1: lift selected card 1 row above the others (deferred C1).
    # When `selection` is set, output has card_h + 1 rows; the selected card
    # paints at rows [0..card_h-1] while the others paint at rows [1..card_h].
    # Blank cells are bare spaces so the felt background shows through.
    has_lift = selection is not None and 0 <= selection < len(cards)
    n_rows = layout.card_h + 1 if has_lift else layout.card_h
    blank_card_line = " " * layout.card_w

    rows: list[str] = []
    for row_idx in range(n_rows):
        if has_lift:
            parts: list[str] = []
            for i, group in enumerate(card_line_groups):
                src_idx = row_idx if i == selection else row_idx - 1
                if 0 <= src_idx < layout.card_h:
                    parts.append(group[src_idx])
                else:
                    parts.append(blank_card_line)
            raw = gap.join(parts)
        else:
            raw = gap.join(group[row_idx] for group in card_line_groups)
        rows.append(ansi_center(raw, term_w))  # ← ANSI-aware centering

    if selection is not None and 0 <= selection < len(cards):
        # Highlight bar — `card_w` cells in highlight_bg directly under the
        # selected card. ANSI-positioned via leading spaces; no escape pollution
        # past the bar because we RESET at the end.
        if show_bar:
            bar_col = left_pad + selection * slot_w
            rows.append(" " * bar_col + highlight_bg() + " " * layout.card_w + RESET)

        if show_readout:
            card = cards[selection]
            is_trump = trump is not None and (card.suit == trump or trump == Suit.TOUT_ATOUT)
            is_legal = card in legal_set
            suit_color = gold_fg() if is_trump else (red_fg() if card.suit.is_red else white_fg())
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


def _up_card_column(
    up_card: Card, center_w: int, mat_height: int, layout: LayoutPreset
) -> list[str]:
    """Bidding: the face-up card centred in the mat area, same height as the
    mat so nothing jumps when play starts. 4.11.0: rows are padded to the full
    centre width — they used to be 20 cells, pulling EAST's column (and the
    card) towards the left on wide terminals."""
    blank = " " * center_w
    body = [ansi_center(f"{light_gray_fg()}UP CARD{RESET}", center_w), blank]
    body += [ansi_center(row, center_w) for row in _get_card_face(up_card, layout=layout)]
    top = max(0, (mat_height - len(body)) // 2)
    rows = [blank] * top + body
    rows += [blank] * (mat_height - len(rows))
    return rows[:mat_height]


def _render_middle_section(
    state: GameState,
    term_w: int,
    layout: LayoutPreset = STANDARD,
    *,
    term_h: int | None = None,
    framed: bool | None = None,
    labels: bool = True,
) -> list[str]:
    """Build the 3-column middle section: WEST | green felt mat | EAST.

    `framed` / `labels` come from `layout.fit_table` (render passes them);
    `framed=None` keeps the old rule (frame when there are 2 spare rows)."""
    west_hand = state.hand_of(Seat.WEST)
    east_hand = state.hand_of(Seat.EAST)

    side_col_w = layout.side_col_w
    center_w = max(0, term_w - side_col_w * 2)
    if framed is None:
        if term_h is None:
            _, term_h = TERMINAL.get_size()
        framed = term_h >= layout.min_rows + 2
    mat_height = (6 if labels else 4) + 3 * layout.card_h
    if framed and mat_is_framed(center_w):
        mat_height += 2

    # ── Center column (trick area / bidding up-card) ──────────────────────────
    center_rows: list[str] = []
    if state.phase == Phase.BIDDING and state.up_card:
        center_rows = _up_card_column(state.up_card, center_w, mat_height, layout)
    else:
        trick = state.current_trick
        seat_map: dict[Seat, Card] = {tc.seat: tc.card for tc in trick}
        masked = masked_seats(state)
        if framed:
            center_rows = _render_trick_mat_framed(
                seat_map, center_w, layout, labels=labels, masked=masked
            )
        else:
            center_rows = _render_trick_mat(
                seat_map, center_w, layout, labels=labels, masked=masked
            )

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


def _north_line(state: GameState, term_w: int, *, show_hand: bool = False) -> str:
    """NORTH's row: label, face-down backs (or the open hand), card count."""
    north_hand = state.hand_of(Seat.NORTH)
    if show_hand:
        north_cards = " ".join(_card_symbol(c) for c in north_hand)
    else:
        north_cards = f"{_card_back_small()} " * min(len(north_hand), 4)
    north_label = _seat_label(Seat.NORTH, state)
    north_count = f"{light_gray_fg()}({len(north_hand)} cards){RESET}"
    return ansi_center(f"{north_label}  {north_cards}  {north_count}", term_w)


def _hand_number_row(n_cards: int, term_w: int, layout: LayoutPreset) -> str:
    """ "[1] [2] …" with each number centred over its card (4.11.0 — the old
    row was one centred block, so the numbers drifted off their cards)."""
    slot_w = layout.card_w + layout.card_gap
    hand_w = n_cards * slot_w - layout.card_gap
    left = max(0, (term_w - hand_w) // 2)
    cells = "".join(f"[{i + 1}]".center(slot_w)[:slot_w] for i in range(n_cards))
    return " " * left + cells.rstrip()


def _south_lines(
    state: GameState,
    selection: int | None,
    term_w: int,
    term_h: int,
    layout: LayoutPreset,
    *,
    readout: bool | None = None,
    bar: bool = True,
    hints: bool = True,
) -> list[str]:
    """SOUTH's block: number hints, the hand (legal cards lit), the label.

    The optional rows come from `layout.fit_table` (render passes them);
    `readout=None` keeps the old rule (only when the terminal has slack)."""
    lines: list[str] = []
    south_hand = state.hand_of(Seat.SOUTH)
    if south_hand:
        south_legal: tuple[Card, ...] = ()
        if state.phase == Phase.PLAYING and state.turn == Seat.SOUTH:
            south_legal = legal_cards(state, Seat.SOUTH)
        if hints:
            lines.append(_hand_number_row(len(south_hand), term_w, layout))
        if readout is None:
            readout = term_h > layout.min_rows
        lines.extend(
            _render_hand_horizontal(
                south_hand,
                selection,
                south_legal,
                term_w,
                layout,
                trump=state.trump,
                show_readout=readout,
                show_bar=bar,
            )
        )
    # The label already reads "You" — the old " (you)" suffix doubled it.
    lines.append(ansi_center(_seat_label(Seat.SOUTH, state), term_w))
    return lines
