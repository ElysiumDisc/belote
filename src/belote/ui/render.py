from __future__ import annotations

import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..ansi import (
    RESET,
    ansi_center,
    clear_to_eol,
    hide_cursor,
    move,
    show_cursor,
    visible_len,
)
from ..ansi import (
    clear_screen as _clear_screen,
)
from ..context import TERMINAL
from ..deck import Card
from ..game import (
    GameState,
    Phase,
    Seat,
)
from ..themes import theme_manager
from .cards import (
    _FACE_ART as _FACE_ART,
)
from .cards import (
    _PIP_ART as _PIP_ART,
)
from .cards import (
    _card_back as _card_back,
)
from .cards import (
    _card_back_small as _card_back_small,
)
from .cards import (
    _card_face_internal as _card_face_internal,
)

# 4.11.0: split into cards / table / hud_classic; re-exported for callers.
from .cards import (
    _card_symbol as _card_symbol,
)
from .cards import (
    _get_card_face as _get_card_face,
)
from .cards import card_back_lines
from .hud_classic import (
    _bid_hint_provider as _bid_hint_provider,
)
from .hud_classic import (
    _bid_lines as _bid_lines,
)
from .hud_classic import (
    _build_bid_prompt_lines as _build_bid_prompt_lines,
)
from .hud_classic import (
    _build_hud as _build_hud,
)
from .hud_classic import (
    _fit_hud as _fit_hud,
)
from .hud_classic import (
    _phase_info as _phase_info,
)
from .hud_classic import (
    set_bid_hint_provider as set_bid_hint_provider,
)
from .layout import TableFit, choose_layout, fit_table, vcenter_lines
from .table import (
    _BRAILLE_DOTS as _BRAILLE_DOTS,
)
from .table import (
    _VIGNETTE_WIDTH as _VIGNETTE_WIDTH,
)
from .table import (
    _felt_blank_internal as _felt_blank_internal,
)
from .table import (
    _felt_pad_ns as _felt_pad_ns,
)
from .table import (
    _felt_placeholder as _felt_placeholder,
)
from .table import (
    _felt_segment as _felt_segment,
)
from .table import (
    _felt_segment_cached as _felt_segment_cached,
)
from .table import (
    _north_line as _north_line,
)
from .table import (
    _pip_at as _pip_at,
)
from .table import (
    _render_hand_horizontal as _render_hand_horizontal,
)
from .table import (
    _render_middle_section as _render_middle_section,
)
from .table import (
    _render_trick_mat as _render_trick_mat,
)
from .table import (
    _render_trick_mat_framed as _render_trick_mat_framed,
)
from .table import (
    _seat_label as _seat_label,
)
from .table import (
    _slot_anchors as _slot_anchors,
)
from .table import (
    _slot_frame_row as _slot_frame_row,
)
from .table import (
    _slot_label_ns as _slot_label_ns,
)
from .table import (
    _south_lines as _south_lines,
)
from .table import (
    _trick_row_offsets as _trick_row_offsets,
)
from .table import (
    _we_row as _we_row,
)
from .table import masked_seats, mat_is_framed

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


@dataclass(frozen=True)
class _MatGeometry:
    """Where the last render() put the trick mat, for `patch_trick_card`.

    4.11.0: recorded instead of re-derived. The old re-derivation repeated
    render()'s spacer thresholds by hand and ignored the decorative frame, so
    whenever the frame was on, every patched card landed one row too high
    (and one column off) until the next full redraw."""

    first_row: int  # index of the middle section's first line (pre-centering)
    fit: TableFit
    framed: bool
    rows_budget: int  # the height the table was fitted to


# 4.11.0: rows an expansion paints over the table (top, bottom), e.g.
# BelAtro's joker strip / trust bar at the top and its score tally at the
# bottom. The top count includes the table's own HUD + rule rows, which the
# overlay replaces by design. Installed per run via `set_overlay_provider`;
# read on every frame so a visibility toggle (BelAtro's I key) applies at once.
_overlay_provider: Callable[[], tuple[int, int]] | None = None


def set_overlay_provider(provider: Callable[[], tuple[int, int]] | None) -> None:
    """Install (or clear, with None) the expansion overlay-rows provider."""
    global _overlay_provider
    _overlay_provider = provider
    invalidate_diff()


def _overlay_rows() -> tuple[int, int]:
    if _overlay_provider is None:
        return (0, 0)
    top, bottom = _overlay_provider()
    return max(0, top), max(0, bottom)


def _table_budget(term_h: int) -> tuple[int, int, int]:
    """(rows the table may use, blank rows to keep under the HUD rule, blank
    rows to keep at the bottom) for the current overlays."""
    top, bottom = _overlay_rows()
    top_extra = max(0, top - 2)  # the overlay covers the table's HUD + rule
    return max(1, term_h - top_extra - bottom), top_extra, bottom


_last_mat_geometry: _MatGeometry | None = None


def _rule_with(text: str, width: int) -> str:
    """A horizontal rule with `text` centred in it: ──── text ────."""
    label = f" {text} " if text else ""
    side = max(0, width - visible_len(label))
    return "─" * (side // 2) + label + "─" * (side - side // 2)


def _center_w(fit: TableFit) -> int:
    term_w, _ = get_term_size()
    return max(0, term_w - fit.layout.side_col_w * 2)


def get_term_size() -> tuple[int, int]:
    """Get terminal size, using cached value if available."""
    return TERMINAL.get_size()


def _handle_sigwinch(_signum: int, _frame: object) -> None:
    """Invalidate terminal size cache on resize."""
    TERMINAL.clear_cache()


if hasattr(signal, "SIGWINCH"):
    signal.signal(signal.SIGWINCH, _handle_sigwinch)


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


def slide_card_to_table_hint(reader: object | None = None) -> None:
    """4.8.0 / C3: brief vertical sparkle trail from south's hand toward the
    south trick slot, painted just before the played card lands at its
    destination.

    Deliberately doesn't try to slide the actual card frame — restoring the
    felt-pip background under multi-row card frames is fragile across
    terminals (Konsole's alt-screen handling especially). Instead we paint a
    short tactile trail of ✦/✧ glyphs along the slot anchor's vertical axis,
    which gives the play a 'launches upward' feel without risking visual
    artifacts. Cheap (~120ms, 4 frames, skippable) and self-cleaning.
    """
    import sys as _sys

    from ..ansi import RESET, gold_fg, move
    from .anim import animations_enabled

    if not animations_enabled():
        return

    term_w, term_h = get_term_size()
    # Bottom-of-hand to mid-screen vertical axis at the centre column.
    col = max(1, term_w // 2)
    start_row = max(2, term_h - 4)
    # Three rows is enough to read as motion without crossing the south slot
    # label and clobbering it.
    end_row = max(2, start_row - 3)
    if start_row <= end_row:
        return

    has_reader = reader is not None and hasattr(reader, "read_timeout")
    glyphs = ("✦", "✧", "✦", "·")
    try:
        for i, row in enumerate(range(start_row, end_row - 1, -1)):
            _sys.stdout.write(move(row, col) + gold_fg() + glyphs[i % len(glyphs)] + RESET)
            _sys.stdout.flush()
            if has_reader:
                event = reader.read_timeout(0.03)  # type: ignore[union-attr]
                if event is not None:
                    break
            else:
                import time as _time

                _time.sleep(0.03)
    finally:
        # Wipe the trail so the next display() repaints over a blank centre
        # column (felt repaint comes via the normal full-frame render).
        for row in range(end_row, start_row + 1):
            _sys.stdout.write(move(row, col) + " ")
        _sys.stdout.flush()
        invalidate_diff()


def pulse_winner_glow(winner: Seat, reader: object | None = None) -> None:
    """4.8.0 / C4: brief gold pulse identifying the trick winner.

    Called from `gameflow.py` after all 4 cards land on the mat and the
    winner is known, BEFORE the trick is swept off the screen. Paints a
    short centered "★ <Direction> wins ★" line at the bottom hint row for
    ~250ms, pulsing gold→white→gold. Skippable; always calls
    `invalidate_diff()` in `finally`.
    """
    import sys as _sys

    from ..ansi import BOLD, RESET, ansi_center, gold_fg, move, white_fg
    from .anim import animations_enabled

    if not animations_enabled():
        return

    term_w, term_h = get_term_size()
    direction = {
        Seat.NORTH: "North",
        Seat.SOUTH: "South",
        Seat.WEST: "West",
        Seat.EAST: "East",
    }[winner]
    row = max(1, term_h - 1)
    body = f"★  {direction} wins the trick  ★"
    frames = (gold_fg() + BOLD, white_fg() + BOLD, gold_fg() + BOLD)

    has_reader = reader is not None and hasattr(reader, "read_timeout")
    try:
        for prefix in frames:
            _sys.stdout.write(move(row, 1) + ansi_center(prefix + body + RESET, term_w))
            _sys.stdout.flush()
            if has_reader:
                event = reader.read_timeout(0.08)  # type: ignore[union-attr]
                if event is not None:
                    return
            else:
                import time as _time

                _time.sleep(0.08)
    finally:
        invalidate_diff()


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
    budget, top_extra, bottom_extra = _table_budget(term_h)
    fit = fit_table(term_w, budget)
    layout = fit.layout

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
    lines: list[str] = []
    # 4.11.0: blank breathing rows only where `fit_table` found room for them
    # (order of value: above the mat, above North, above the divider, under
    # the turn banner). Before 4.11.0 they were keyed on raw terminal height
    # and, with the under-counted presets, pushed the hand off the screen.
    spacer = [i < fit.spacers for i in range(4)]

    # ── HUD ──────────────────────────────────────────────────────────────────
    lines.append(_build_hud(state, term_w, layout))
    lines.append("─" * term_w)
    lines.extend([""] * top_extra)  # under an expansion's top overlay

    # ── NORTH ────────────────────────────────────────────────────────────────
    if spacer[1]:
        lines.append("")
    lines.append(_north_line(state, term_w, show_hand=show_north_hand))

    # ── WEST | trick area | EAST  (3-column, same rows) ──────────────────────
    if spacer[0]:
        lines.append("")
    global _last_mat_geometry
    _last_mat_geometry = _MatGeometry(
        first_row=len(lines),
        fit=fit,
        framed=fit.framed and mat_is_framed(_center_w(fit)),
        rows_budget=budget,
    )
    lines.extend(
        _render_middle_section(state, term_w, layout, framed=fit.framed, labels=fit.mat_labels)
    )

    # ── DIVIDER + PHASE INFO ──────────────────────────────────────────────────
    if spacer[2]:
        lines.append("")
    if fit.phase_row:
        lines.append("─" * term_w)
        lines.append(ansi_center(_phase_info(state), term_w))
    else:  # last resort: the turn banner rides in the divider
        lines.append(_rule_with(_phase_info(state), term_w))
    if spacer[3]:
        lines.append("")

    # ── SOUTH hand ────────────────────────────────────────────────────────────
    lines.extend(
        _south_lines(
            state,
            selection,
            term_w,
            term_h,
            layout,
            readout=fit.readout,
            bar=fit.hand_bar,
            hints=fit.hints,
        )
    )

    # ── BIDDING PROMPT ────────────────────────────────────────────────────────
    # Bidding never shows the lifted card / bar / readout, so this row (and a
    # spacer above it when there was room for any) always fits.
    if state.phase == Phase.BIDDING and state.turn == Seat.SOUTH:
        if fit.spacers:
            lines.append("")
        lines.extend(_bid_lines(state, term_w, bid_selection))

    # ── Vertical centering ──────────────────────────────────────────────────
    # If the terminal is taller than the rendered content, pad top + bottom so
    # the game centers vertically instead of clinging to the top.
    if top_extra or bottom_extra:
        # Expansion overlays sit at fixed rows, so instead of centring the
        # whole frame, centre the table body in the window between them and
        # fill the screen exactly (the HUD stays on rows 1-2 under the overlay).
        head = 2 + top_extra
        pad = max(0, (term_h - bottom_extra - len(lines)) // 2)
        lines[head:head] = [""] * pad
        if _last_mat_geometry is not None:
            _last_mat_geometry = replace(
                _last_mat_geometry, first_row=_last_mat_geometry.first_row + pad
            )
        lines += [""] * max(0, term_h - len(lines))
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
    rendered_lines: tuple[str, ...] = tuple(line + clear_to_eol() for line in lines[:term_h])
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


def display_hud(
    state: GameState,
    *,
    team_scores_override: tuple[int, int] | None = None,
) -> None:
    """Targeted update of only the top HUD bar.

    `team_scores_override` is the score-roll animation hook (4.6.5) — lets
    callers paint intermediate scores without allocating a fresh frozen
    GameState per frame via `dataclasses.replace`.
    """
    term_w, term_h = get_term_size()
    layout = choose_layout(term_w, term_h)
    sys.stdout.write(
        move(1, 1) + _build_hud(state, term_w, layout, team_scores_override=team_scores_override)
    )
    sys.stdout.flush()


# Diff-based emit toggle. Resolved once from the env at import (it used to be
# re-read on every frame); the Settings screen flips it via set_diff_enabled.
_DIFF_ENABLED: bool = os.environ.get("BELOTE_NO_DIFF") != "1"


def set_diff_enabled(on: bool) -> None:
    global _DIFF_ENABLED, _last_emitted_lines
    _DIFF_ENABLED = on
    _last_emitted_lines = None  # next frame is a full redraw either way


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
    * the "Fast redraw" setting off, or env var `BELOTE_NO_DIFF=1` — escape
      hatch for debugging artifact complaints (read once, not per frame).

    Layout/theme changes invalidate the baseline automatically (render()
    + the theme_manager callback both set `_last_emitted_lines = None`).
    """
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
        and _DIFF_ENABLED
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


def _slot_origin(geo: _MatGeometry, seat: Seat, term_w: int, term_h: int) -> tuple[int, int]:
    """1-indexed (row, col) of `seat`'s card on screen, from the geometry
    the last render() recorded."""
    layout = geo.fit.layout
    border = 1 if geo.framed else 0
    center_w = max(0, term_w - layout.side_col_w * 2)
    inner_w = center_w - 2 * border
    n_s_start, w_start, e_start = _slot_anchors(inner_w, layout.card_w)
    # Mat rows: slot frame, ["N"], N card, slot frame, W/E cards, slot frame,
    # S card, ["S"], slot frame — see `_render_trick_mat`.
    labels = 1 if geo.fit.mat_labels else 0
    ch = layout.card_h
    n_row = 1 + labels
    we_row = n_row + ch + 1
    s_row = we_row + ch + 1
    rel = {
        Seat.NORTH: (n_row, n_s_start),
        Seat.WEST: (we_row, w_start),
        Seat.EAST: (we_row, e_start),
        Seat.SOUTH: (s_row, n_s_start),
    }[seat]
    top_pad = 0
    if _last_rendered_unpadded_h and _last_rendered_unpadded_h < term_h - 1:
        top_pad = ((term_h - 1) - _last_rendered_unpadded_h) // 2
    row = top_pad + geo.first_row + border + rel[0] + 1
    col = layout.side_col_w + border + rel[1] + 1
    return row, col


def patch_trick_card(state: GameState, seat: Seat, card: Card, *, force_hud: bool = False) -> None:
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
    geo = _last_mat_geometry
    budget, _, _ = _table_budget(term_h)
    if geo is None or geo.rows_budget != budget or geo.fit != fit_table(term_w, budget):
        # No render yet at this size (or the terminal was resized since):
        # a full frame is both correct and cheap here.
        display(state, None)
        return
    layout = geo.fit.layout
    row, col = _slot_origin(geo, seat, term_w, term_h)
    # Build the whole patch as a single string and emit one stdout.write so
    # signal-interruptible terminals (Konsole especially) can't paint half the
    # card before the HUD update lands. Pre-3.5.0 each card-face line + the HUD
    # update were separate writes, which produced torn frames under load.
    face = (
        card_back_lines(layout)
        if seat in masked_seats(state)
        else _get_card_face(card, layout=layout)
    )
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
