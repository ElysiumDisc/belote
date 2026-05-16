from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Literal

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    hide_cursor,
    red_fg,
    visible_len,
    white_fg,
)
from ..deck import Card, Suit
from ..game import (
    GameState,
    RoundScore,
    Seat,
    legal_cards,
    sort_south_hand,
)
from ..input import Key, KeyReader
from ..rules import RULES_CONTENT, RulesPage
from ..themes import THEMES, theme_manager
from .card_detail import show_card_detail
from .render import display, get_term_size, invalidate_diff


def prompt_card(
    state: GameState, reader: KeyReader, show_north_hand: bool = False
) -> tuple[Card | Literal["UNDO", "OVERLAY"] | None, GameState]:
    """Interactive card selection with arrow keys.

    Returns (card, state) where state may differ from the input if the hand was
    sorted during selection. Callers should propagate the returned state.
    Returns (None, state) if QUIT is pressed.
    """
    # Auto-sort the south hand on entry so cards are always grouped by suit
    # (trump first) and rank. sort_south_hand returns a new frozen state; the
    # docstring above already commits callers to propagating it.
    state = sort_south_hand(state)
    hand = state.hand_of(Seat.SOUTH)
    legal = legal_cards(state, Seat.SOUTH)

    if not hand:
        raise ValueError("No cards in hand")
    if not legal:
        return hand[0], state

    # Start selection on the first legal card
    sel = next((i for i, c in enumerate(hand) if c in legal), 0)

    while True:
        display(state, sel, show_north_hand=show_north_hand)
        event = reader.read()

        match event.key:
            case Key.QUIT | Key.EOF:
                # EOF (closed stdin) is treated as a quit so the loop doesn't
                # spin re-reading a dead pipe forever.
                return None, state
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
                    return hand[sel], state
                # Fallback: return nearest legal card
                for delta in range(1, len(hand)):
                    for d in (delta, -delta):
                        idx = sel + d
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            return hand[idx], state
            case Key.HELP:
                show_help(reader)
                continue
            case Key.SORT:
                selected_card = hand[sel]
                state = sort_south_hand(state)
                hand = state.hand_of(Seat.SOUTH)
                legal = legal_cards(state, Seat.SOUTH)
                # Re-find selection index
                sel = next((i for i, c in enumerate(hand) if c == selected_card), 0)
                continue
            case Key.THEME:
                themes_list = list(THEMES.keys())
                curr_theme = theme_manager.current_name
                new_idx = (themes_list.index(curr_theme) + 1) % len(themes_list)
                theme_manager.set_current(themes_list[new_idx])
                continue
            case Key.HIST:
                show_history(state, reader)
                continue
            case Key.OVERLAY:
                return "OVERLAY", state
            case Key.CARD_DETAIL:
                if hand and 0 <= sel < len(hand):
                    show_card_detail(hand[sel], reader)
                continue
            case Key.CHAR:
                if event.char:
                    char = event.char.lower()
                    if char == "z":
                        return "UNDO", state
                    if char.isdigit():
                        idx = int(char) - 1
                        if 0 <= idx < len(hand) and hand[idx] in legal:
                            return hand[idx], state
    # Unreachable: the while(True) above only exits via return.
    raise AssertionError("prompt_card loop fell through without returning")


def prompt_bid(state: GameState, reader: KeyReader) -> Suit | str | None:
    """Interactive bid selection. Returns 'QUIT' if QUIT is pressed.

    Round 2 offers Tout Atout (TA) and Sans Atout (SA) in addition to the
    three remaining card suits. Per FFBelote rules, round 1 is "take the
    up-card suit at the standard contract" only — TA/SA aren't offered there.

    The selector UI is painted by render() (via display(..., bid_selection=sel))
    so each frame is a single in-place repaint. Writing additional lines after
    display() would scroll the alt-screen on stricter terminals (Konsole) and
    leak previous frames onto blank padding rows.
    """
    from ..game import SANS_ATOUT_BID

    if state.bidding_round == 1:
        options: list[Suit | str | None] = [state.up_card.suit, None]  # type: ignore[union-attr]
    else:
        all_suits = [Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS]
        other_suits = [s for s in all_suits if s != state.up_card.suit]  # type: ignore[union-attr]
        options = [*other_suits, Suit.TOUT_ATOUT, SANS_ATOUT_BID, None]

    sel = 0

    while True:
        display(state, None, bid_selection=sel)

        event = reader.read()
        match event.key:
            case Key.QUIT | Key.EOF:
                # EOF (closed stdin) is treated as a quit so the bid loop
                # doesn't spin re-reading a dead pipe.
                return "QUIT"
            case Key.LEFT | Key.UP:
                sel = (sel - 1) % len(options)
            case Key.RIGHT | Key.DOWN:
                sel = (sel + 1) % len(options)
            case Key.ENTER:
                return options[sel]
            case Key.HELP:
                show_help(reader)
                continue
            case Key.THEME:
                themes_list = list(THEMES.keys())
                curr_theme = theme_manager.current_name
                new_idx = (themes_list.index(curr_theme) + 1) % len(themes_list)
                theme_manager.set_current(themes_list[new_idx])
                continue
            case Key.HIST:
                show_history(state, reader)
                continue
            case Key.OVERLAY:
                return "OVERLAY"
            case Key.CARD_DETAIL:
                if state.up_card is not None:
                    show_card_detail(state.up_card, reader)
                continue
            case Key.CHAR:
                if event.char:
                    char = event.char.lower()
                    if char == "z":
                        return "UNDO"
                    if char == "p":
                        return None
                    # Round-2-only quick keys for the new contracts. `a` = All
                    # trump (Tout Atout), `s` = Sans Atout. Silently ignored in
                    # round 1 since those contracts aren't legal there.
                    if char == "a" and Suit.TOUT_ATOUT in options:
                        return Suit.TOUT_ATOUT
                    if char == "s" and SANS_ATOUT_BID in options:
                        return SANS_ATOUT_BID
                    try:
                        idx = int(char) - 1
                        if 0 <= idx < len(options):
                            return options[idx]
                    except ValueError:
                        pass


def show_help(reader: KeyReader) -> None:
    """Display a quick keyboard shortcut reference."""
    term_w, term_h = get_term_size()

    lines = [
        f"{BOLD}{gold_fg()}KEYBOARD SHORTCUTS{RESET}",
        "=" * 20,
        "",
        f"{white_fg()}General:{RESET}",
        "  [?]         Show this help screen",
        "  [Q]         Quit to menu / Exit",
        "  [T]         Cycle Theme",
        "  [Esc]       Cancel / Back",
        "",
        f"{white_fg()}Gameplay:{RESET}",
        "  [←↑→↓]      Move selection",
        "  [Enter]     Confirm selection",
        "  [1-8]       Quick card select",
        "  [O]         Sort hand by suit/rank",
        "  [Space]     Skip animations",
        "  [H]         View Game History",
        "  [F]         View card detail (Grimaud art)",
        "  [Z]         Undo last move",
        "",
        f"{white_fg()}Bidding:{RESET}",
        "  [P]         Pass",
        "  [1-4]       Bid suit (S/H/D/C)",
        "",
        f"{white_fg()}Menus:{RESET}",
        "  [H]         View Game History",
        "",
        f"{DIM}Press [Any Key] to Return{RESET}",
    ]

    out = clear_screen() + hide_cursor()
    rendered = "\r\n".join(ansi_center(line, term_w) for line in lines)
    sys.stdout.write("".join([out, rendered]))
    sys.stdout.flush()
    reader.read()
    invalidate_diff()


def show_rules(reader: KeyReader) -> None:
    """Display scrollable rules and history in EN/FR."""
    lang = "en"
    scroll = 0

    # Pre-render both languages
    cached_renders: dict[tuple[str, int], list[str]] = {}

    def get_render(lang_key: str, wrap_at: int) -> list[str]:
        if (lang_key, wrap_at) in cached_renders:
            return cached_renders[(lang_key, wrap_at)]

        content: RulesPage = RULES_CONTENT[lang_key]
        lines = []
        lines.append(f"{BOLD}{gold_fg()}{content['title']}{RESET}")
        lines.append("=" * visible_len(content["title"]))
        lines.append("")

        for section in content["sections"]:
            lines.append(f"{BOLD}{white_fg()}{section['header']}{RESET}")
            lines.append("-" * len(section["header"]))
            # Wrap text manually
            words = section["text"].split()
            line = "  "
            for w in words:
                if len(line) + len(w) > wrap_at:
                    lines.append(line)
                    line = "  " + w + " "
                else:
                    line += w + " "
            lines.append(line)
            lines.append("")

        lines.append(
            f"{DIM}Press [L] to Toggle Language ({lang_key.upper()}) | [Q/Enter] Back{RESET}"
        )
        cached_renders[(lang_key, wrap_at)] = lines
        return lines

    while True:
        term_w, term_h = get_term_size()
        wrap_at = min(80, term_w - 8)
        all_lines = get_render(lang, wrap_at)
        # Window the lines
        view_h = term_h - 4
        scroll = max(0, min(scroll, len(all_lines) - view_h))
        visible_lines = all_lines[scroll : scroll + view_h]

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible_lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.QUIT | Key.ENTER | Key.ESC | Key.EOF:
                invalidate_diff()
                return
            case Key.HELP:
                show_help(reader)
            case Key.UP:
                scroll = max(0, scroll - 1)
            case Key.DOWN:
                scroll = min(len(all_lines) - view_h, scroll + 1)
            case Key.CHAR:
                if event.char and event.char.lower() == "l":
                    lang = "fr" if lang == "en" else "en"
                    scroll = 0


def _hist_taker_label(rs: RoundScore) -> str:
    team = "NS" if rs.taker_team == 0 else "EW"
    if rs.taker_seat is None:
        return team
    return f"{rs.taker_seat.name[0]} ({team})"


def _hist_contract_label(rs: RoundScore) -> str:
    if rs.contract == "sans_atout":
        return "SA"
    if rs.contract == "tout_atout":
        return "TA"
    sym = rs.trump.symbol if rs.trump is not None and hasattr(rs.trump, "symbol") else "?"
    return f"NORM {sym}"


def _hist_status(rs: RoundScore) -> str:
    if rs.is_capot:
        return f"{gold_fg()}CAPOT{RESET}"
    if rs.is_failed:
        return f"{red_fg()}CHUTE{RESET}"
    if rs.is_litige:
        return f"{DIM}LITIGE{RESET}"
    return "─"


def _hist_decl_str(items: tuple[str, ...], width: int) -> str:
    if not items:
        return "─"
    s = " ".join(items)
    if len(s) > width:
        s = s[: max(0, width - 1)] + "…"
    return s


def _ljust_visible(s: str, width: int) -> str:
    pad = max(0, width - visible_len(s))
    return s + " " * pad


# 3.3.0: dispatch hook for the [H] overlay. BelAtro registers its own
# renderer (reading BelAtroRun.history) because state.score_history is
# never populated under the BelAtro round driver. None ⇒ classic path.
_history_override: Callable[[KeyReader], None] | None = None


def set_history_override(renderer: Callable[[KeyReader], None] | None) -> None:
    """Install (or clear with ``None``) the [H]-key history renderer.

    Used by BelAtro to swap in its per-blind history view; the classic
    Belote path leaves this as ``None`` and falls through to
    ``state.score_history`` rendering.
    """
    global _history_override
    _history_override = renderer


def _build_history_lines(state: GameState, term_w: int) -> list[str]:
    """Build the static line list for the history overlay.

    Extracted so `show_history` can cache the result across scroll-loop
    iterations — pre-4.1.0 the same lines were rebuilt on every keystroke,
    which on 60+ round games was the dominant per-input cost in the modal.
    Rebuild keyed only on (term_w, len(state.score_history)).
    """
    lines: list[str] = []
    lines.append(f"{BOLD}{gold_fg()}GAME HISTORY{RESET}")
    lines.append("=" * 12)
    lines.append("")

    if not state.score_history:
        lines.append(f"{DIM}No rounds completed yet.{RESET}")
        lines.append("")
        lines.append(f"{DIM}[↑↓] Scroll  [Any Key] Return{RESET}")
        return lines

    wide = term_w >= 78
    if wide:
        # Single-row layout. Column widths sum to ~76 with separators.
        w_rd, w_tkr, w_con, w_trk, w_decl, w_ns, w_ew, w_st = 3, 7, 8, 7, 16, 5, 5, 7
        header_cells = [
            _ljust_visible("RD", w_rd),
            _ljust_visible("TAKER", w_tkr),
            _ljust_visible("CONTRACT", w_con),
            _ljust_visible("TRICKS", w_trk),
            _ljust_visible("DECLARATIONS", w_decl),
            _ljust_visible("NS", w_ns),
            _ljust_visible("EW", w_ew),
            _ljust_visible("STATUS", w_st),
        ]
        header = " │ ".join(header_cells)
        lines.append(f"{BOLD}{white_fg()}{header}{RESET}")
        lines.append("─" * visible_len(header))

        for i, rs in enumerate(state.score_history):
            rd = f"{i + 1:02d}"
            taker = _hist_taker_label(rs)
            contract = _hist_contract_label(rs)
            tricks = f"{rs.tricks_ns} / {rs.tricks_ew}"
            decl_ns = _hist_decl_str(rs.decl_summary_ns, w_decl // 2 - 1)
            decl_ew = _hist_decl_str(rs.decl_summary_ew, w_decl // 2 - 1)
            if rs.decl_summary_ns and rs.decl_summary_ew:
                decls = f"{decl_ns} / {decl_ew}"
            elif rs.decl_summary_ns:
                decls = decl_ns
            elif rs.decl_summary_ew:
                decls = decl_ew
            else:
                decls = "─"
            if visible_len(decls) > w_decl:
                decls = decls[: w_decl - 1] + "…"
            ns = f"{BOLD}{rs.ns_total}{RESET}"
            ew = f"{BOLD}{rs.ew_total}{RESET}"
            status = _hist_status(rs)

            row_cells = [
                _ljust_visible(rd, w_rd),
                _ljust_visible(taker, w_tkr),
                _ljust_visible(contract, w_con),
                _ljust_visible(tricks, w_trk),
                _ljust_visible(decls, w_decl),
                _ljust_visible(ns, w_ns),
                _ljust_visible(ew, w_ew),
                _ljust_visible(status, w_st),
            ]
            lines.append(" │ ".join(row_cells))
    else:
        # Compact two-line-per-round layout for narrow terminals.
        lines.append(f"{BOLD}{white_fg()}{'RD':<3} {'TAKER':<7} {'CON':<8} {'TRICKS':<7} STATUS{RESET}")
        lines.append("─" * 40)
        for i, rs in enumerate(state.score_history):
            rd = f"{i + 1:02d}"
            taker = _hist_taker_label(rs)
            contract = _hist_contract_label(rs)
            tricks = f"{rs.tricks_ns}/{rs.tricks_ew}"
            status = _hist_status(rs)
            lines.append(
                f"{rd:<3} {_ljust_visible(taker, 7)} {contract:<8} {tricks:<7} {status}"
            )
            decl_n = _hist_decl_str(rs.decl_summary_ns, 14)
            decl_e = _hist_decl_str(rs.decl_summary_ew, 14)
            lines.append(
                f"   NS:{BOLD}{rs.ns_total:>4}{RESET}  EW:{BOLD}{rs.ew_total:>4}{RESET}  "
                f"decl: {decl_n} / {decl_e}"
            )
            lines.append("")

    lines.append("")
    lines.append(f"{DIM}[↑↓] Scroll  [Any Key] Return{RESET}")
    return lines


def show_history(state: GameState, reader: KeyReader) -> None:
    """Display a scrollable overlay of round-by-round scores."""
    if _history_override is not None:
        _history_override(reader)
        return
    scroll = 0
    # 4.1.0 (C5): cache the line list across scroll iterations. Rebuild only
    # when the cache key changes (term_w toggles between wide/narrow layout,
    # or new rounds get added). State is immutable during the modal so this
    # is safe and shaves the dominant per-keystroke cost.
    cache_key: tuple[int, int] | None = None
    cached_lines: list[str] = []

    while True:
        term_w, term_h = get_term_size()
        key = (term_w, len(state.score_history))
        if key != cache_key:
            cached_lines = _build_history_lines(state, term_w)
            cache_key = key

        lines = cached_lines
        view_h = term_h - 4
        max_scroll = max(0, len(lines) - view_h)
        scroll = max(0, min(scroll, max_scroll))
        visible_lines = lines[scroll : scroll + view_h]

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible_lines)
        sys.stdout.write("".join([out, rendered]))
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.UP:
                scroll = max(0, scroll - 1)
            case Key.DOWN:
                scroll = min(max_scroll, scroll + 1)
            case _:
                invalidate_diff()
                return
