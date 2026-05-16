"""Grimaud-style zoomed card detail view.

Press `F` while a card is under the cursor (play or bid phase) to open a
full-screen modal with a hand-drawn half-block rendering of that card.

Each of the 12 face cards (J/Q/K × 4 suits) has a unique combination of
silhouette template, palette, and held object loosely inspired by the
GRIMAUD Standard 1898 plate. Non-face cards (7-A) get a scaled-up pip
layout. Any key dismisses the popup; the caller re-renders the game frame
on the next loop iteration.

Rendering uses the half-block trick: each terminal cell encodes TWO
stacked pixels — the top pixel via the foreground color of `▀`, the bottom
pixel via the background color. So the 18×24 pixel art interior becomes
18×12 cell rows.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    bg,
    clear_screen,
    felt_bg,
    fg,
    hide_cursor,
    move,
)
from ..deck import Card, Rank, Suit
from .fit_guard import require_minimum
from .render import get_term_size, invalidate_diff

if TYPE_CHECKING:
    from ..input import KeyReader


# ----------------------------------------------------------------------------
# Canvas dimensions
# ----------------------------------------------------------------------------
# Popup is CARD_W cells wide × CARD_H cells tall. Inside the border we render
# an ART_W × ART_H pixel grid; pixels stack 2-per-cell vertically via ▀.
ART_W = 18
ART_H = 24
ART_CELL_H = ART_H // 2  # 12 cell rows of half-blocks
CARD_W = ART_W + 2       # outer width = inner art + 2 border cells
CARD_H = ART_CELL_H + 4  # +2 borders, +2 index rows


# ----------------------------------------------------------------------------
# Palette colors (24-bit RGB)
# ----------------------------------------------------------------------------
RGB = tuple[int, int, int]

BG_PARCHMENT: RGB = (248, 238, 212)   # card face cream
INK: RGB = (38, 26, 18)
SKIN: RGB = (242, 212, 174)
SKIN_DK: RGB = (200, 158, 118)
GOLD: RGB = (210, 168, 56)
GOLD_HI: RGB = (244, 212, 96)
WHITE: RGB = (245, 240, 232)

# Suit palettes — primary robe color + accent
RED: RGB = (188, 32, 38)
RED_DK: RGB = (130, 18, 22)
BLUE: RGB = (28, 64, 132)
BLUE_DK: RGB = (12, 32, 90)
GREEN: RGB = (44, 116, 64)
GREEN_DK: RGB = (16, 64, 32)
PURPLE: RGB = (96, 40, 116)
PURPLE_DK: RGB = (52, 18, 72)

# Hair tones
HAIR_BR: RGB = (78, 48, 22)
HAIR_GREY: RGB = (210, 198, 188)
HAIR_BLOND: RGB = (210, 168, 88)

# Held-object accents
SILVER: RGB = (210, 210, 220)
SILVER_DK: RGB = (140, 140, 150)


SUIT_ROBE: dict[Suit, tuple[RGB, RGB]] = {
    Suit.HEARTS: (RED, RED_DK),
    Suit.SPADES: (BLUE, BLUE_DK),
    Suit.DIAMONDS: (GREEN, GREEN_DK),
    Suit.CLUBS: (PURPLE, PURPLE_DK),
}


# ----------------------------------------------------------------------------
# Half-block compiler
# ----------------------------------------------------------------------------
def _compile_art(pixels: list[str], palette: dict[str, RGB]) -> list[str]:
    """Compile an ART_H × ART_W pixel grid into ART_CELL_H half-block rows.

    Each character in `pixels[y]` is a key in `palette`. '.' means
    transparent (use BG_PARCHMENT).
    """
    if len(pixels) != ART_H:
        raise ValueError(f"Expected {ART_H} pixel rows, got {len(pixels)}")
    out: list[str] = []
    for y in range(0, ART_H, 2):
        top = pixels[y]
        bot = pixels[y + 1]
        if len(top) != ART_W or len(bot) != ART_W:
            raise ValueError(
                f"Pixel rows must be exactly {ART_W} wide; got "
                f"{len(top)}/{len(bot)} at y={y}"
            )
        parts: list[str] = []
        for x in range(ART_W):
            tp = palette.get(top[x], BG_PARCHMENT)
            bp = palette.get(bot[x], BG_PARCHMENT)
            parts.append(f"{fg(*tp)}{bg(*bp)}▀{RESET}")
        out.append("".join(parts))
    return out


# ----------------------------------------------------------------------------
# Silhouette templates
# ----------------------------------------------------------------------------
# Pixel-grid characters used in templates:
#   '.' transparent (parchment)
#   'O' outline (INK)
#   'S' skin
#   's' skin shadow
#   'C' crown / gold
#   'c' gold highlight
#   'H' hair / beard
#   'R' robe primary
#   'r' robe dark
#   'W' white trim
#   '1'..'4' per-card object slots (filled in by held-object overlay)

# Each template is 18×24. Held-object slot rendered as ' ' (whitespace) so
# overlays can paint on top via the per-card object_pixels.

_KING_TEMPLATE = [
    "..................",  # 0
    ".....C..C..C......",  # 1  crown spikes
    "....C2C2C2C2C.....",  # 2  spikes w/ jewels
    "....CCCCCCCCC.....",  # 3  crown bridge
    "...CC2.C2.C2.CC...",  # 4  crown band jewels
    "...CCCCCCCCCCC....",  # 5  crown band
    "....HHHHHHHHH.....",  # 6  hair top
    "...HHSSSSSSSHH....",  # 7  hair + forehead
    "...HSOSSSSSOSH....",  # 8  face + eyes
    "...HSSSsssSSSH....",  # 9  face mid
    "....SSSssSSSS.....",  # 10 nose
    "....SSOOOOSSS.....",  # 11 mouth
    "....HHHHHHHHH.....",  # 12 beard top
    "...HHHHHHHHHHH....",  # 13 beard
    "....HHHHHHHHH.....",  # 14 beard tip
    "...rRRRRRRRRRr....",  # 15 collar
    "..rRWRRRRRRWRr....",  # 16 robe with ermine
    "..rRRRRRRRRRRRr...",  # 17 robe
    "..rRRWWWWWRRRRr...",  # 18 robe sash
    "..rRRRRRRRRRRRr...",  # 19 robe
    "..rrRRRRRRRRRrr...",  # 20 robe taper
    "...rrRRRRRRRrr....",  # 21 robe bottom
    "....rrrRRRrrr.....",  # 22 hem
    ".....rrrrrrr......",  # 23 base
]

_QUEEN_TEMPLATE = [
    "..................",  # 0
    "......C.C.C.......",  # 1  crown three peaks
    "....CCCCCCCCC.....",  # 2  crown peaks bridge
    "....C2.C2.C2.C....",  # 3  crown jewels
    "....CCCCCCCCC.....",  # 4  crown band
    ".....HHHHHHHH.....",  # 5  hair bun line
    "....HHHHHHHHHH....",  # 6  hair frame top
    "...HHHSSSSSSSHH...",  # 7  hair frame
    "...HSSSSSSSSSSH...",  # 8  forehead
    "...HSOSSSSSSOSH...",  # 9  eyes
    "...HSSSSssSSSSH...",  # 10 nose
    "....SSSSssSSSS....",  # 11 cheeks
    "....SSSOOOOSSS....",  # 12 mouth
    "....HHsssssHHH....",  # 13 chin / neck
    "...rRRRRRRRRRr....",  # 14 collar
    "..rRRRRRRRRRRRr...",  # 15 shoulders
    "..rRRRWWWWRRRRr...",  # 16 bodice w/ trim
    "..rRRWWWWWWWRRr...",  # 17 bodice center
    "..rRRWWccccWRRr...",  # 18 bodice w/ jewels (gold)
    "..rRRRRRRRRRRRr...",  # 19 waist
    "..rrRRRRRRRRRrr...",  # 20 skirt
    "...rRRRRRRRRRr....",  # 21 skirt taper
    "....rrRRRRrr......",  # 22 hem
    ".....rrrrrr.......",  # 23 base
]

_JACK_TEMPLATE = [
    "..................",  # 0
    "....CC............",  # 1  hat plume base
    "...C2CC...........",  # 2  hat ornament + feather
    "..CCRRCCC.........",  # 3  hat front (red sash)
    "..CCRRRRRCC.......",  # 4  hat brim
    "..CCRRRRRRRCC.....",  # 5  hat wide brim
    "....HHHHHHHHH.....",  # 6  hair under brim
    "...HSSSSSSSSSH....",  # 7  forehead
    "...HSOSSSSSOSH....",  # 8  eyes
    "...HSSSssSSSSH....",  # 9  nose
    "....SSsssssSS.....",  # 10 face
    "....SSOOOOSS......",  # 11 mouth
    "....HHHHHHHH......",  # 12 chin / hair side
    "....HHHHHHHHH.....",  # 13 hair locks
    "...rRRRRRRRRRr....",  # 14 collar
    "..rRRRRRRRRRRRr...",  # 15 shoulders
    "..rRWWRRRRRWWRr...",  # 16 doublet w/ slashes
    "..rRWWRRRRRWWRr...",  # 17 doublet slashes
    "..rRRRRRRRRRRRr...",  # 18 waist
    "..rRRccccccRRRr...",  # 19 belt (gold)
    "..rrRRRRRRRRRrr...",  # 20 skirt of doublet
    "...rRRRRRRRRRr....",  # 21 taper
    "....rrRRRRrr......",  # 22 hem
    ".....rrrrrr.......",  # 23 base
]


# ----------------------------------------------------------------------------
# Held-object overlays — drawn on top of the silhouette to the RIGHT side
# ----------------------------------------------------------------------------
# Each entry maps (row, col) → palette key. Cols 13-17 are reserved for the
# held object slot; the templates above leave that area mostly empty.

# Hearts — flower / leaf / scepter-w-heart
_HELD_HEART_FLOWER = {  # ♥Q
    (13, 14): "F", (13, 15): "F",
    (14, 13): "F", (14, 14): "f", (14, 15): "F", (14, 16): "F",
    (15, 13): "F", (15, 14): "F", (15, 15): "F", (15, 16): "F",
    (16, 14): "F", (16, 15): "F",
    (17, 14): "G", (17, 15): "G",
    (18, 14): "G", (18, 15): "G",
    (19, 15): "G",
    (20, 15): "G",
}

_HELD_HEART_SCEPTER = {  # ♥K
    (4, 16): "c",
    (5, 16): "F", (5, 15): "F", (5, 17): "F",
    (6, 16): "F",
    (7, 16): "c",
    (8, 16): "c",
    (9, 16): "c",
    (10, 16): "c",
    (11, 16): "c",
    (12, 16): "c",
    (13, 16): "c",
    (14, 16): "c",
    (15, 16): "c",
    (16, 16): "c",
}

_HELD_HEART_LEAF = {  # ♥J
    (2, 15): "G", (2, 16): "G",
    (3, 15): "G", (3, 16): "G", (3, 17): "G",
    (4, 14): "G", (4, 15): "G", (4, 16): "G",
    (5, 15): "G",
    (6, 15): "G",
    (7, 15): "G",
    (8, 15): "G",
}

# Spades — sword / halberd / scepter
_HELD_SPADE_SWORD = {  # ♠K — sword held vertical
    (1, 15): "M",
    (2, 15): "M",
    (3, 15): "M",
    (4, 15): "M",
    (5, 15): "M",
    (6, 15): "M",
    (7, 15): "M",
    (8, 15): "M",
    (9, 15): "M",
    (10, 14): "m", (10, 15): "c", (10, 16): "m",  # crossguard (gold)
    (11, 15): "c",
    (12, 14): "c", (12, 15): "c", (12, 16): "c",  # pommel
}

_HELD_SPADE_SCEPTER = {  # ♠Q
    (3, 16): "c",
    (4, 16): "c",
    (5, 16): "M",
    (6, 16): "M",
    (7, 16): "M",
    (8, 16): "M",
    (9, 16): "M",
    (10, 16): "M",
    (11, 16): "M",
    (12, 16): "M",
    (13, 16): "M",
    (14, 16): "c",
}

_HELD_SPADE_HALBERD = {  # ♠J
    (1, 15): "M", (1, 16): "M",
    (2, 14): "M", (2, 15): "M", (2, 16): "M", (2, 17): "M",
    (3, 14): "M", (3, 15): "M", (3, 16): "M", (3, 17): "M",
    (4, 15): "M", (4, 16): "M",
    (5, 16): "m",
    (6, 16): "m",
    (7, 16): "m",
    (8, 16): "m",
    (9, 16): "m",
}

# Diamonds — axe / fan / scroll
_HELD_DIAMOND_AXE = {  # ♦K
    (3, 14): "M", (3, 15): "M", (3, 16): "M", (3, 17): "M",
    (4, 13): "M", (4, 14): "M", (4, 15): "M", (4, 16): "M", (4, 17): "M",
    (5, 14): "m", (5, 15): "m", (5, 16): "m", (5, 17): "m",
    (6, 16): "m",
    (7, 16): "m",
    (8, 16): "m",
    (9, 16): "m",
    (10, 16): "m",
    (11, 16): "m",
}

_HELD_DIAMOND_FAN = {  # ♦Q (striped headdress + fan held aloft)
    (2, 14): "c", (2, 16): "c",
    (3, 13): "c", (3, 14): "F", (3, 15): "c", (3, 16): "F", (3, 17): "c",
    (4, 13): "F", (4, 14): "c", (4, 15): "F", (4, 16): "c", (4, 17): "F",
    (5, 13): "c", (5, 14): "F", (5, 15): "c", (5, 16): "F", (5, 17): "c",
    (6, 14): "F", (6, 15): "F", (6, 16): "F",
}

_HELD_DIAMOND_SCROLL = {  # ♦J
    (4, 15): "F", (4, 16): "F",
    (5, 14): "F", (5, 15): "F", (5, 16): "F",
    (6, 14): "F", (6, 15): "F", (6, 16): "F",
    (7, 15): "F", (7, 16): "F",
    (8, 15): "F",
    (9, 15): "F",
    (10, 15): "F",
}

# Clubs — orb / fan / bow
_HELD_CLUB_ORB = {  # ♣K
    (4, 14): "c", (4, 15): "c", (4, 16): "c",
    (5, 13): "c", (5, 14): "c", (5, 15): "c", (5, 16): "c", (5, 17): "c",
    (6, 13): "c", (6, 14): "c", (6, 15): "F", (6, 16): "c", (6, 17): "c",
    (7, 13): "c", (7, 14): "c", (7, 15): "c", (7, 16): "c", (7, 17): "c",
    (8, 14): "c", (8, 15): "c", (8, 16): "c",
    (9, 16): "m",
    (10, 16): "m",
    (11, 16): "m",
}

_HELD_CLUB_FEATHERFAN = {  # ♣Q
    (1, 15): "F",
    (2, 14): "F", (2, 15): "F", (2, 16): "F",
    (3, 13): "F", (3, 14): "F", (3, 15): "F", (3, 16): "F", (3, 17): "F",
    (4, 13): "F", (4, 14): "F", (4, 15): "F", (4, 16): "F", (4, 17): "F",
    (5, 14): "F", (5, 15): "F", (5, 16): "F",
    (6, 15): "m",
    (7, 15): "m",
    (8, 15): "m",
    (9, 15): "m",
}

_HELD_CLUB_BOW = {  # ♣J
    (4, 15): "M", (4, 16): "M",
    (5, 14): "M", (5, 17): "M",
    (6, 14): "M", (6, 17): "M",
    (7, 13): "M", (7, 14): "M", (7, 15): "F", (7, 16): "F", (7, 17): "M",
    (8, 14): "M", (8, 17): "M",
    (9, 14): "M", (9, 17): "M",
    (10, 15): "M", (10, 16): "M",
}


# ----------------------------------------------------------------------------
# Per-face-card configuration
# ----------------------------------------------------------------------------
def _build_palette(suit: Suit, *, hair: RGB, accent: RGB) -> dict[str, RGB]:
    """Build a palette dict for a face card. `accent` colors held-object
    flower/leaf areas (F/f); G is leaf-green for hearts, m/M are silver."""
    robe_main, robe_dk = SUIT_ROBE[suit]
    return {
        "O": INK,
        "S": SKIN,
        "s": SKIN_DK,
        "C": GOLD,
        "c": GOLD_HI,
        "2": (220, 40, 60) if suit.is_red else SILVER,  # crown jewels
        "H": hair,
        "R": robe_main,
        "r": robe_dk,
        "W": WHITE,
        "F": accent,
        "f": (255, 220, 90),  # flower center / highlight
        "G": (44, 132, 64),    # leaf green
        "M": SILVER,
        "m": SILVER_DK,
    }


# Each entry: (template, hair_color, accent_color_for_object, object_overlay)
_FACE_DESIGNS: dict[tuple[Rank, Suit], tuple[list[str], RGB, RGB, dict[tuple[int, int], str]]] = {
    (Rank.KING, Suit.HEARTS):   (_KING_TEMPLATE,  HAIR_GREY,  RED,    _HELD_HEART_SCEPTER),
    (Rank.QUEEN, Suit.HEARTS):  (_QUEEN_TEMPLATE, HAIR_BLOND, RED,    _HELD_HEART_FLOWER),
    (Rank.JACK, Suit.HEARTS):   (_JACK_TEMPLATE,  HAIR_BLOND, RED,    _HELD_HEART_LEAF),
    (Rank.KING, Suit.SPADES):   (_KING_TEMPLATE,  HAIR_BR,    SILVER, _HELD_SPADE_SWORD),
    (Rank.QUEEN, Suit.SPADES):  (_QUEEN_TEMPLATE, HAIR_BR,    SILVER, _HELD_SPADE_SCEPTER),
    (Rank.JACK, Suit.SPADES):   (_JACK_TEMPLATE,  HAIR_BR,    SILVER, _HELD_SPADE_HALBERD),
    (Rank.KING, Suit.DIAMONDS): (_KING_TEMPLATE,  HAIR_BLOND, GOLD,   _HELD_DIAMOND_AXE),
    (Rank.QUEEN, Suit.DIAMONDS):(_QUEEN_TEMPLATE, HAIR_BR,    RED,    _HELD_DIAMOND_FAN),
    (Rank.JACK, Suit.DIAMONDS): (_JACK_TEMPLATE,  HAIR_BLOND, GOLD,   _HELD_DIAMOND_SCROLL),
    (Rank.KING, Suit.CLUBS):    (_KING_TEMPLATE,  HAIR_GREY,  GOLD,   _HELD_CLUB_ORB),
    (Rank.QUEEN, Suit.CLUBS):   (_QUEEN_TEMPLATE, HAIR_BR,    PURPLE, _HELD_CLUB_FEATHERFAN),
    (Rank.JACK, Suit.CLUBS):    (_JACK_TEMPLATE,  HAIR_BR,    GOLD,   _HELD_CLUB_BOW),
}


def _apply_overlay(
    grid: list[str], overlay: dict[tuple[int, int], str]
) -> list[str]:
    """Return a new pixel grid with `overlay` painted over `grid`."""
    rows = [list(r) for r in grid]
    for (y, x), ch in overlay.items():
        if 0 <= y < ART_H and 0 <= x < ART_W:
            rows[y][x] = ch
    return ["".join(r) for r in rows]


# ----------------------------------------------------------------------------
# Pip / Ace renderer (procedural for 7-10 + A)
# ----------------------------------------------------------------------------
_PIP_LAYOUTS: dict[Rank, list[tuple[int, int]]] = {
    # (row, col) positions for each suit-symbol pip, centered in 18×24 grid
    Rank.SEVEN: [(4, 5), (4, 12), (10, 5), (10, 12), (16, 5), (16, 12), (8, 8)],
    Rank.EIGHT: [(3, 5), (3, 12), (9, 5), (9, 12), (15, 5), (15, 12), (6, 8), (12, 8)],
    Rank.NINE:  [(3, 5), (3, 12), (8, 5), (8, 12), (13, 5), (13, 12), (18, 5), (18, 12), (10, 8)],
    Rank.TEN:   [(3, 5), (3, 12), (7, 5), (7, 12), (11, 5), (11, 12), (15, 5), (15, 12), (19, 5), (19, 12)],
}


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
def _suit_color(suit: Suit) -> RGB:
    return RED if suit.is_red else INK


def _face_lines(card: Card) -> list[str]:
    """Half-block art lines for a face card (12 lines tall)."""
    design = _FACE_DESIGNS.get((card.rank, card.suit))
    if design is None:
        raise KeyError(f"No face design for {card}")
    template, hair, accent, overlay = design
    grid = _apply_overlay(template, overlay)
    palette = _build_palette(card.suit, hair=hair, accent=accent)
    return _compile_art(grid, palette)


def _pip_lines(card: Card) -> list[str]:
    """Plain-text pip / ace rendering (12 lines tall, ART_W wide visible)."""
    suit_sym = card.suit.symbol
    suit_c = _suit_color(card.suit)
    pip_str = f"{fg(*suit_c)}{bg(*BG_PARCHMENT)}{BOLD}{suit_sym}{RESET}"
    blank_cell = f"{bg(*BG_PARCHMENT)} {RESET}"

    # Build a 12×18 character grid
    grid = [[blank_cell] * ART_W for _ in range(ART_CELL_H)]

    if card.rank == Rank.ACE:
        # Large stylized A with central suit symbol
        ace_art = [
            "                  ",
            "      ▄█▀█▄       ",
            "     ▄█   █▄      ",
            "    ▄█  ♥  █▄     ",
            "    █████████     ",
            "    █       █     ",
            "    █       █     ",
            "    █       █     ",
            "                  ",
            "    " + suit_sym + " A " + suit_sym + "          ",
            "                  ",
            "                  ",
        ]
        out: list[str] = []
        for line in ace_art:
            line = line.replace("♥", suit_sym)
            out.append(f"{fg(*suit_c)}{bg(*BG_PARCHMENT)}{line[:ART_W].ljust(ART_W)}{RESET}")
        return out

    layout = _PIP_LAYOUTS.get(card.rank, [])
    # Translate pixel-space (row in 0..23, col in 0..17) to half-block cell
    # rows by dividing row by 2.
    for (py, px) in layout:
        cy = min(py // 2, ART_CELL_H - 1)
        cx = min(px, ART_W - 1)
        grid[cy][cx] = pip_str

    return ["".join(row) for row in grid]


def _render_card(card: Card) -> list[str]:
    """Render the full popup body (CARD_H lines, CARD_W cells visible)."""
    is_face = card.rank in (Rank.JACK, Rank.QUEEN, Rank.KING)
    art = _face_lines(card) if is_face else _pip_lines(card)

    inner_w = CARD_W - 2
    border_color = fg(*INK) + bg(*BG_PARCHMENT)
    top = f"{border_color}╔{'═' * inner_w}╗{RESET}"
    bot = f"{border_color}╚{'═' * inner_w}╝{RESET}"
    border_v = f"{border_color}║{RESET}"
    blank = f"{bg(*BG_PARCHMENT)}{' ' * inner_w}{RESET}"

    suit_sym = card.suit.symbol
    rank_str = card.rank.value
    suit_c = _suit_color(card.suit)
    idx_color = fg(*suit_c) + bg(*BG_PARCHMENT) + BOLD
    tl_text = f"{idx_color}{rank_str}{suit_sym}{RESET}"
    br_text = f"{idx_color}{suit_sym}{rank_str}{RESET}"
    idx_vis = 3 if rank_str == "10" else 2

    tl_row = (
        f"{border_v}{tl_text}"
        f"{bg(*BG_PARCHMENT)}{' ' * (inner_w - idx_vis)}{RESET}{border_v}"
    )
    br_row = (
        f"{border_v}{bg(*BG_PARCHMENT)}{' ' * (inner_w - idx_vis)}{RESET}"
        f"{br_text}{border_v}"
    )

    art_rows = [f"{border_v}{line}{border_v}" for line in art]

    rows = [top, tl_row, *art_rows, br_row, bot]
    while len(rows) < CARD_H:
        rows.insert(-1, f"{border_v}{blank}{border_v}")
    return rows[:CARD_H]


def show_card_detail(card: Card, reader: KeyReader) -> None:
    """Open a full-screen Grimaud-style detail view for `card`.

    Blocks until any key is pressed. The caller is expected to re-issue its
    last `display()` to restore the game frame afterwards.
    """
    # Guard against tiny terminals (popup itself fits easily in 80×32, but
    # honor the global floor for consistency with show_help / show_history).
    require_minimum(reader, 80, 32)

    term_w, term_h = get_term_size()

    rank_word = {
        Rank.SEVEN: "SEVEN", Rank.EIGHT: "EIGHT", Rank.NINE: "NINE",
        Rank.TEN: "TEN", Rank.JACK: "JACK", Rank.QUEEN: "QUEEN",
        Rank.KING: "KING", Rank.ACE: "ACE",
    }[card.rank]
    suit_word = {
        Suit.HEARTS: "HEARTS", Suit.SPADES: "SPADES",
        Suit.DIAMONDS: "DIAMONDS", Suit.CLUBS: "CLUBS",
        Suit.TOUT_ATOUT: "TOUT ATOUT",
    }[card.suit]

    title = (
        f"{BOLD}{fg(*_suit_color(card.suit))}"
        f"{card.suit.symbol} {rank_word} OF {suit_word} {card.suit.symbol}"
        f"{RESET}"
    )
    subtitle = f"{DIM}Grimaud Standard 1898{RESET}"
    footer = f"{DIM}[any key] back{RESET}"

    body = _render_card(card)

    # Vertical centering
    extra = max(0, term_h - (len(body) + 4))
    top_pad = extra // 2

    # Paint felt across every row first, so the parchment card pops against
    # the table felt (matches the 3.9.4 felt-mat aesthetic).
    felt_row = felt_bg() + " " * term_w + RESET
    felt_fill = "".join(move(r, 1) + felt_row for r in range(1, term_h + 1))

    out = [clear_screen(), hide_cursor(), felt_fill]
    row = max(1, top_pad)
    out.append(move(row, 1) + ansi_center(title, term_w))
    out.append(move(row + 1, 1) + ansi_center(subtitle, term_w))
    for i, line in enumerate(body):
        out.append(move(row + 3 + i, 1) + ansi_center(line, term_w))
    out.append(move(row + 3 + len(body) + 1, 1) + ansi_center(footer, term_w))

    sys.stdout.write("".join(out))
    sys.stdout.flush()
    reader.read()

    # We wrote directly to stdout, bypassing render.display(). Without this
    # call, the next display() would diff the new game frame against the
    # pre-popup cached frame, see "no rows changed", and write nothing —
    # leaving the popup visible behind a partial game redraw (the "two
    # stacks of cards" symptom).
    invalidate_diff()
