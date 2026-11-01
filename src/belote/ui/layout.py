"""Responsive layout system.

Four preset tiers — mini / compact / standard / spacious — keyed on terminal
size. Card sizes, side-column widths, and HUD verbosity are all driven by the
chosen preset.

4.11.0: the table is fitted to the terminal *height* by `fit_table`, which
picks the largest preset whose essential rows fit and then adds optional rows
(highlight bar, mat labels, card readout, decorative frame, blank spacers)
while they still fit. Before 4.11.0 the presets' `min_rows` under-counted the
table by 2-8 rows, so at every size the bottom of the hand (and the bid
selector) was cut off. `min_rows` is now the exact essential height
(`12 + 4 × card_h`), so the smallest terminal the classic game accepts is a
plain 80×24 (MINI, 3-row cards).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LayoutPreset:
    name: str

    # Card dimensions (visible cells, including borders)
    card_w: int
    card_h: int
    card_gap: int

    # Width reserved for the West/East side columns in the middle section
    side_col_w: int

    # Minimum terminal size at which this preset is selectable
    min_cols: int
    min_rows: int

    # HUD verbosity: "verbose" (full labels) or "compact" (abbreviated one-liner).
    # The STANDARD preset uses "compact" because the verbose HUD (~132 chars)
    # overflows at 96 cols — "verbose" only fires at spacious widths.
    hud_style: str

    # Whether the W/E "Last Trick" sidebar shows in side columns at this size.
    # At compact widths we hide it — the user can press H for full history.
    show_last_trick_sidebar: bool


# Essential table rows: HUD + rule (2), North (1), tight mat (4 + 3·ch),
# rule (1), turn banner (1), number hints (1), hand + lift (ch + 1), South (1).
def _essential_rows(card_h: int) -> int:
    return 12 + 4 * card_h


MINI = LayoutPreset(
    name="mini",
    card_w=6,
    card_h=3,
    card_gap=1,
    side_col_w=14,
    min_cols=80,
    min_rows=_essential_rows(3),  # 24 — a default 80×24 terminal
    hud_style="compact",
    show_last_trick_sidebar=False,
)

COMPACT = LayoutPreset(
    name="compact",
    card_w=6,
    card_h=5,
    card_gap=1,
    side_col_w=16,
    min_cols=80,
    min_rows=_essential_rows(5),  # 32
    hud_style="compact",
    show_last_trick_sidebar=False,
)

STANDARD = LayoutPreset(
    name="standard",
    card_w=9,
    card_h=7,
    card_gap=1,
    side_col_w=22,
    min_cols=96,
    min_rows=_essential_rows(7),  # 40
    # The full-verbose HUD is ~132 chars — overflows at 96. Keep the compact
    # one-line form here too; verbose form only fires at spacious widths.
    hud_style="compact",
    show_last_trick_sidebar=True,
)

SPACIOUS = LayoutPreset(
    name="spacious",
    card_w=11,
    card_h=9,
    card_gap=2,
    side_col_w=26,
    min_cols=120,
    min_rows=_essential_rows(9),  # 48
    hud_style="verbose",
    show_last_trick_sidebar=True,
)


# Ordered largest-first so `choose_layout` picks the most generous fit.
ALL_LAYOUTS: tuple[LayoutPreset, ...] = (SPACIOUS, STANDARD, COMPACT, MINI)


# Hard floor for the classic game — smaller terminals get the resize prompt.
# (Expansion screens may ask for more via `require_minimum`.)
MIN_COLS = MINI.min_cols
MIN_ROWS = MINI.min_rows


def choose_layout(cols: int, rows: int) -> LayoutPreset:
    """Return the largest preset that fits in (cols, rows). Falls back to MINI.

    Callers are responsible for rejecting terminals below (MIN_COLS, MIN_ROWS)
    *before* calling this — at that point MINI itself doesn't render cleanly.
    """
    for preset in ALL_LAYOUTS:
        if cols >= preset.min_cols and rows >= preset.min_rows:
            return preset
    return MINI


@dataclass(frozen=True)
class TableFit:
    """Which optional rows the classic table draws at this terminal size.

    Heights are for the tallest moment (SOUTH choosing a card); bidding is
    shorter, so one fit holds for the whole round and nothing jumps."""

    layout: LayoutPreset
    hand_bar: bool = True  # highlight bar under the selected card
    mat_labels: bool = True  # the "N" / "S" rows inside the trick mat
    readout: bool = True  # "► A♠ — Trump ◄" under the hand
    framed: bool = True  # decorative frame around the mat (+2 rows)
    spacers: int = 4  # blank breathing rows, filled in a fixed order
    hints: bool = True  # "[1] [2] …" row above the hand (last resort)
    phase_row: bool = True  # turn banner on its own row (last resort)

    @property
    def mat_rows(self) -> int:
        ch = self.layout.card_h
        return (6 if self.mat_labels else 4) + 3 * ch + (2 if self.framed else 0)

    @property
    def height(self) -> int:
        ch = self.layout.card_h
        hand = ch + 1 + int(self.hand_bar) + int(self.readout)
        return (
            2  # HUD + rule
            + 1  # North
            + self.mat_rows
            + 1  # rule
            + int(self.phase_row)
            + int(self.hints)
            + hand
            + 1  # South label
            + self.spacers
        )


MAX_SPACERS = 4


def fit_table(cols: int, rows: int) -> TableFit:
    """The richest table that fits `rows` (see `TableFit`).

    Largest preset whose essential rows fit, then optional rows in order of
    value (bar, mat labels, readout, frame, spacers) while they still fit —
    leaving the bottom row free for banners when possible. If even MINI's
    essentials don't fit, the number-hint row and then the separate turn
    banner are dropped (the caller still clips as a last resort)."""
    layout = choose_layout(cols, rows)
    bare = TableFit(
        layout, hand_bar=False, mat_labels=False, readout=False, framed=False, spacers=0
    )
    if bare.height > rows:
        bare = replace(bare, hints=False)
        if bare.height > rows:
            bare = replace(bare, phase_row=False)
        return bare
    fit = bare
    budget = rows - 1 if rows > bare.height else rows  # keep a banner row free
    upgrades: list[Callable[[TableFit], TableFit]] = [
        lambda f: replace(f, hand_bar=True),
        lambda f: replace(f, mat_labels=True),
        lambda f: replace(f, readout=True),
    ]
    if layout is not MINI:  # no room across for a border at 3-row cards
        upgrades.append(lambda f: replace(f, framed=True))
    for upgrade in upgrades:
        candidate = upgrade(fit)
        if candidate.height <= budget:
            fit = candidate
    while fit.spacers < MAX_SPACERS and fit.height + 1 <= budget:
        fit = replace(fit, spacers=fit.spacers + 1)
    return fit


def fits_minimum(cols: int, rows: int) -> bool:
    """True iff the terminal is at least the compact-preset minimum."""
    return cols >= MIN_COLS and rows >= MIN_ROWS


def vcenter_lines(lines: list[str], term_h: int) -> list[str]:
    """Pad `lines` top + bottom with blanks so the block sits centered in
    `term_h`; truncate to `term_h` if the content overflows.

    Mirrors the centering math in `ui/render.py` (slack budget = `term_h - 1`).
    """
    rendered_h = len(lines)
    if rendered_h < term_h - 1:
        slack = (term_h - 1) - rendered_h
        top_pad = slack // 2
        bottom_pad = slack - top_pad
        lines = [""] * top_pad + lines + [""] * bottom_pad
    return lines[:term_h]
