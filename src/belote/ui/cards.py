"""Card glyphs: faces, backs and the per-theme render caches.

Split out of `ui/render.py` in 4.11.0. Everything here is a pure function of
(card, flags, theme name, glyph set, card size, card back id), so results are
`lru_cache`d; `render.clear_card_cache()` flushes them on a theme change. The
names stay importable from `belote.ui.render` for compatibility.
"""

from __future__ import annotations

from functools import lru_cache

from .. import cosmetics
from ..ansi import (
    DIM,
    RESET,
    bg,
    black_fg,
    card_face_bg,
    face_card_bg,
    fg,
    highlight_bg,
    palette,
    red_fg,
)
from ..context import TERMINAL
from ..cosmetics import DEFAULT_BACK, CardBack, ColorRef, TableFrame, card_back
from ..deck import Card, Rank
from ..themes import theme_manager
from .layout import STANDARD, LayoutPreset

# 4.1.0 (perf): `theme_manager.current_name` cached as a module-local so the
# per-card / per-felt-row cache keys skip a property lookup. Refreshed by the
# callback below on every theme change.
_cached_theme_name: str = theme_manager.current_name


def _refresh_theme_name_cache() -> None:
    global _cached_theme_name
    _cached_theme_name = theme_manager.current_name


theme_manager.register_callback(_refresh_theme_name_cache)

# 4.11.0: the active card back / table frame, refreshed by the cosmetics
# callback (`settings.apply` → `cosmetics.set_active`). Render caches key on
# the back id, so a change needs no cache flush.
_cached_back: CardBack = cosmetics.active_back()
_cached_frame: TableFrame = cosmetics.active_frame()


def _refresh_cosmetics_cache() -> None:
    global _cached_back, _cached_frame
    _cached_back = cosmetics.active_back()
    _cached_frame = cosmetics.active_frame()


cosmetics.register_callback(_refresh_cosmetics_cache)


def _card_symbol(card: Card) -> str:

    suit_str = card.suit.symbol if TERMINAL.has_utf8 else card.suit.name[0]
    return f"{card.rank.value}{suit_str}"


# Centre art for the full-size (card_h >= 7) face, "{s}" = suit glyph.
# Face cards + Ace: (utf8 top, ascii top, middle, utf8 bottom, ascii bottom).
_FACE_ART: dict[Rank, tuple[str, str, str, str, str]] = {
    Rank.JACK: ("╭━┳━╮", " ***  ", "{s}J{s}", "╰─┃─╯", " -|-  "),  # knave with sword
    Rank.QUEEN: ("╭◊─◊╮", " (-)  ", "{s}Q{s}", "╰─♥─╯", " -v-  "),  # jewelled headdress
    Rank.KING: ("╭┻━┻╮", " /=\\  ", "{s}K{s}", "╰─┴─╯", " ---  "),  # crown
    Rank.ACE: ("╭─◆─╮", "*-+-*", " {s}A{s} ", "╰─◆─╯", "*-+-*"),  # wreath
}
# Pip cards: three rows of suit pips in a recognisable pattern.
_PIP_ART: dict[Rank, tuple[str, str, str]] = {
    Rank.SEVEN: ("{s}   {s}", "  {s}  ", "{s}   {s}"),
    Rank.EIGHT: ("{s}   {s}", "{s}   {s}", "{s}   {s}"),
    Rank.NINE: ("{s} {s} {s}", "{s}   {s}", "{s} {s} {s}"),
    Rank.TEN: ("{s} {s} {s}", "{s} {s} {s}", "{s}   {s}"),
}


@lru_cache(maxsize=8192)
def _card_face_internal(
    card: Card,
    selected: bool,
    legal: bool,
    theme_name: str,  # noqa: ARG001 — lru_cache key: per-theme colors
    has_utf8: bool,
    card_w: int,
    card_h: int,
) -> list[str]:
    """Render a card as `card_h` lines of width `card_w` (cached).

    `card_h` 3 is the MINI one-line face (4.11.0); ≥ 5 gets index corners.
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

    # 4.11.0 MINI layout (80×24 terminals): 3 rows — border, index, border.
    if card_h <= 3:
        mini = f"{rank_str}{suit_sym}".center(inner_w)[:inner_w].ljust(inner_w)
        return [top_border, _line(mini), bottom_border][:card_h]

    # Standard / spacious: room for 3-row centre art between the index corners.
    # Compact (card_h <= 5): just index corners and a single suit row.
    if card_h >= 7:
        face = _FACE_ART.get(card.rank)
        if face is not None:
            utf_top, ascii_top, mid, utf_bot, ascii_bot = face
            raw = (utf_top if has_utf8 else ascii_top, mid, utf_bot if has_utf8 else ascii_bot)
        else:
            raw = _PIP_ART.get(card.rank, ("", "{s}", ""))
        # Center, then truncate/pad to inner_w (handles card_w other than 9).
        art_top, art_mid, art_bot = (
            r.replace("{s}", suit_sym).center(inner_w)[:inner_w].ljust(inner_w) for r in raw
        )

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
    """Helper to call cached _card_face with current global state.

    Uses the module-local `_cached_theme_name` (kept in sync by the theme
    callback) instead of the live `theme_manager.current_name` property to
    skip a property lookup + attribute dereference per card render
    (~52 calls per game frame).
    """
    return _card_face_internal(
        card,
        selected,
        legal,
        _cached_theme_name,
        TERMINAL.has_utf8,
        layout.card_w,
        layout.card_h,
    )


def _color(ref: ColorRef, *, background: bool) -> str:
    """Escape for a cosmetic colour: a theme palette field (keeps its own
    fg/bg role), a fixed RGB triple, or None (no escape). NO_COLOR-aware via
    `ansi.fg` / `ansi.bg`."""
    if ref is None:
        return ""
    if isinstance(ref, str):
        return palette(ref)
    return bg(*ref) if background else fg(*ref)


def _back_style(back: CardBack) -> str:
    return _color(back.bg, background=True) + _color(back.fg, background=False)


def _tile(motif: str, width: int) -> str:
    return (motif * (width // len(motif) + 1))[:width]


@lru_cache(maxsize=128)
def _card_back(
    theme_name: str,  # noqa: ARG001 — lru_cache key: per-theme colors
    has_utf8: bool,
    card_w: int,
    card_h: int,
    back_id: str = DEFAULT_BACK,
) -> list[str]:
    """Render a face-down card in the `back_id` design, sized to (card_w, card_h).

    4.11.0: the design comes from `cosmetics.CARD_BACKS`; the default
    "Classique" back is byte-identical to the pre-4.11 single themed back.
    """
    back = card_back(back_id)
    inner_w = card_w - 2
    inner_h = card_h - 2  # rows between the borders
    pattern = back.pattern if has_utf8 else back.pattern_ascii

    if back.centered:
        # One motif centred on every row (the original lattice back).
        row = (" " + pattern[0] + " ").center(inner_w)[:inner_w].ljust(inner_w)
        rows = [row] * inner_h
    else:
        rows = [_tile(pattern[r % len(pattern)], inner_w) for r in range(inner_h)]

    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )
    style = _back_style(back)
    res = [f"{style}{b_tl}{b_h * inner_w}{b_tr}{RESET}"]
    for row in rows:
        res.append(f"{style}{b_v}{row}{b_v}{RESET}")
    res.append(f"{style}{b_bl}{b_h * inner_w}{b_br}{RESET}")
    return res


def card_back_lines(layout: LayoutPreset = STANDARD, back_id: str | None = None) -> list[str]:
    """A full face-down card in the active (or given) back, at `layout` size."""
    return _card_back(
        _cached_theme_name,
        TERMINAL.has_utf8,
        layout.card_w,
        layout.card_h,
        _cached_back.id if back_id is None else back_id,
    )


def card_back_chip(back_id: str | None = None) -> str:
    """The 2-cell face-down chip used for opponents' hands."""
    back = _cached_back if back_id is None else card_back(back_id)
    char = back.small if TERMINAL.has_utf8 else back.small_ascii
    return f"{_back_style(back)}{char}{RESET}"


def _card_back_small() -> str:
    """Single-line face-down card for opponent hand display (active back)."""
    return card_back_chip()
