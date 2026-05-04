"""Responsive layout system.

Three preset tiers — compact / standard / spacious — keyed on terminal size.
`choose_layout(cols, rows)` returns the largest preset that fits. Card sizes,
side-column widths, and HUD verbosity are all driven by the chosen preset.

The minimum terminal we accept is the compact preset's dims (80×32). Below
that, the game refuses to start. Above the spacious threshold (120×48), we
keep using the spacious preset and let `ansi_center` handle the extra space.
"""

from __future__ import annotations

from dataclasses import dataclass


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

    # HUD verbosity: "verbose" (full labels), "standard" (current), "compact" (abbrev)
    hud_style: str

    # Whether the W/E "Last Trick" sidebar shows in side columns at this size.
    # At compact widths we hide it — the user can press T for full history.
    show_last_trick_sidebar: bool


COMPACT = LayoutPreset(
    name="compact",
    card_w=6,
    card_h=5,
    card_gap=1,
    side_col_w=16,
    min_cols=80,
    min_rows=32,
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
    min_rows=38,
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
    min_rows=48,
    hud_style="verbose",
    show_last_trick_sidebar=True,
)


# Ordered largest-first so `choose_layout` picks the most generous fit.
ALL_LAYOUTS: tuple[LayoutPreset, ...] = (SPACIOUS, STANDARD, COMPACT)


# Hard floor — terminals smaller than this are rejected at startup.
MIN_COLS = COMPACT.min_cols
MIN_ROWS = COMPACT.min_rows


def choose_layout(cols: int, rows: int) -> LayoutPreset:
    """Return the largest preset that fits in (cols, rows). Falls back to COMPACT.

    Callers are responsible for rejecting terminals below (MIN_COLS, MIN_ROWS)
    *before* calling this — at that point COMPACT itself doesn't render cleanly.
    """
    for preset in ALL_LAYOUTS:
        if cols >= preset.min_cols and rows >= preset.min_rows:
            return preset
    return COMPACT


def fits_minimum(cols: int, rows: int) -> bool:
    """True iff the terminal is at least the compact-preset minimum."""
    return cols >= MIN_COLS and rows >= MIN_ROWS
