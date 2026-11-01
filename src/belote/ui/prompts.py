from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    ansi_ljust,
    clear_screen,
    gold_fg,
    hide_cursor,
    red_fg,
    visible_len,
    white_fg,
)
from ..deck import Card, Suit
from ..game import (
    BidValue,
    GameState,
    RoundScore,
    S,
    Seat,
    legal_cards,
    sort_south_hand,
    team_of,
)
from ..input import Key, KeyReader, key_label, typed
from ..rules import RULES_CONTENT, RulesPage
from ..themes import theme_manager
from .render import display, get_term_size, invalidate_diff


@dataclass(frozen=True, slots=True)
class ExtensionKey:
    """A key an expansion registered: the prompt returns it unhandled."""

    key: Key


# Keys handed back to the caller instead of being handled (or ignored) by the
# core prompts. Empty in classic play; an expansion registers its own keys
# (BelAtro: the I overlay toggle and the V inventory) for the duration of a
# run and unregisters them on exit.
_EXTENSION_KEYS: set[Key] = set()


def register_extension_keys(*keys: Key) -> None:
    _EXTENSION_KEYS.update(keys)


def unregister_extension_keys(*keys: Key) -> None:
    _EXTENSION_KEYS.difference_update(keys)


def _open_overlay(key: Key, state: GameState, reader: KeyReader) -> None:
    """Help (?), theme cycle (T) and round history (H): shared by the card
    and bid prompts; each returns to the prompt afterwards."""
    if key == Key.HELP:
        show_help(reader)
    elif key == Key.THEME:
        theme_manager.cycle()
    else:
        show_history(state, reader)


def _step_to_legal(hand: tuple[Card, ...], legal: tuple[Card, ...], sel: int, step: int) -> int:
    """Move the selection to the next legal card in `step`'s direction, or
    stay put if there is none that way."""
    new = sel + step
    while 0 <= new < len(hand) and hand[new] not in legal:
        new += step
    return new if 0 <= new < len(hand) else sel


def _nearest_legal(hand: tuple[Card, ...], legal: tuple[Card, ...], sel: int) -> Card | None:
    """The selected card if legal, else the nearest legal one (right first)."""
    if hand[sel] in legal:
        return hand[sel]
    for delta in range(1, len(hand)):
        for d in (delta, -delta):
            idx = sel + d
            if 0 <= idx < len(hand) and hand[idx] in legal:
                return hand[idx]
    return None


def _card_quick_key(
    char: str, hand: tuple[Card, ...], legal: tuple[Card, ...]
) -> Card | Literal["UNDO"] | None:
    """Z = undo; 1-8 = play that card if legal."""
    if char == "z":
        return "UNDO"
    # isdecimal, not isdigit: "²" is a digit but int("²") used to crash here.
    if char.isdecimal():
        idx = int(char) - 1
        if 0 <= idx < len(hand) and hand[idx] in legal:
            return hand[idx]
    return None


class _NoBidKey(Enum):
    """Sentinel: the key isn't a bid shortcut (None is a real bid: pass)."""

    TOKEN = 0


def _bid_quick_key(char: str, options: list[BidValue]) -> BidValue | Literal["UNDO"] | _NoBidKey:
    """Z = undo, P = pass, X = Tout Atout, N = Sans Atout (round 2 only),
    1-n = that option. Returns `_NO_BID_KEY` for anything else.

    4.5.0 moved the TA/SA keys off `a`/`s`: those are WASD aliases."""
    from ..game import SANS_ATOUT_BID

    if char == "z":
        return "UNDO"
    if char == "p":
        return None
    if char == "x" and Suit.TOUT_ATOUT in options:
        return Suit.TOUT_ATOUT
    if char == "n" and SANS_ATOUT_BID in options:
        return SANS_ATOUT_BID
    # isdecimal, not isdigit: "²" is a digit but int("²") raises.
    if char.isdecimal() and 0 <= int(char) - 1 < len(options):
        return options[int(char) - 1]
    return _NoBidKey.TOKEN


def prompt_card(
    state: S,
    reader: KeyReader,
    show_north_hand: bool = False,
    after_display: Callable[[S], None] | None = None,
) -> tuple[Card | Literal["UNDO"] | ExtensionKey | None, S]:
    """Interactive card selection with arrow keys.

    Returns (card, state) where state may differ from the input if the hand was
    sorted during selection. Callers should propagate the returned state.
    Returns (None, state) if QUIT is pressed.

    4.7.0 follow-up: `after_display` runs after every `display()` in the
    selection loop. The BelAtro wrapper uses it to repaint the top HUD and
    the persistent slot-machine tally readout so they stay visible between
    tricks. Classic Belote passes `None` and gets the original behaviour.
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
        # 4.7.1 B2: Belote's suit-follow / overtrump rules guarantee at least
        # one legal card whenever the hand is non-empty. Silently substituting
        # `hand[0]` here would let an illegal card reach `play_card` if
        # `legal_cards` ever regresses. Match the AI-path contract
        # (`ai.py::decide_card`) and fail loudly instead.
        raise AssertionError(
            f"legal_cards returned empty for non-empty hand "
            f"(seat=SOUTH, phase={state.phase}, trump={state.trump}, "
            f"contract={state.contract}, hand_size={len(hand)})"
        )

    # Start selection on the first legal card
    sel = next((i for i, c in enumerate(hand) if c in legal), 0)

    while True:
        display(state, sel, show_north_hand=show_north_hand)
        if after_display is not None:
            after_display(state)
        event = reader.read()
        if event.key in _EXTENSION_KEYS:
            return ExtensionKey(event.key), state

        match event.key:
            case Key.QUIT | Key.EOF:
                # EOF (closed stdin) is treated as a quit so the loop doesn't
                # spin re-reading a dead pipe forever.
                return None, state
            case Key.LEFT | Key.UP:
                sel = _step_to_legal(hand, legal, sel, -1)
            case Key.RIGHT | Key.DOWN:
                sel = _step_to_legal(hand, legal, sel, +1)
            case Key.ENTER:
                card = _nearest_legal(hand, legal, sel)
                if card is not None:
                    return card, state
            case Key.HELP | Key.THEME | Key.HIST:
                _open_overlay(event.key, state, reader)
            case Key.SORT:
                selected_card = hand[sel]
                state = sort_south_hand(state)
                hand = state.hand_of(Seat.SOUTH)
                legal = legal_cards(state, Seat.SOUTH)
                # Re-find selection index
                sel = next((i for i, c in enumerate(hand) if c == selected_card), 0)
            case Key.CHAR if event.char:
                choice = _card_quick_key(event.char.lower(), hand, legal)
                if choice is not None:
                    return choice, state
    # Unreachable: the while(True) above only exits via return.
    raise AssertionError("prompt_card loop fell through without returning")


def prompt_coinche(state: GameState, reader: KeyReader) -> bool:
    """4.9.0 / G1: ask SOUTH (defender) whether to coinche the locked bid.

    Called from `gameflow.py::run_bidding` after a bid is taken and SOUTH
    is on the defending team. Returns True iff the player chose to coinche.
    Pressing C / ENTER without C / ESC all keep behavior simple: C =
    coinche, anything else = pass.
    """
    if state.taker is None:
        return False
    # `Seat.name` is "East"/"West" (display case), so compare teams, not names.
    taker_label = "EW" if team_of(state.taker) == 1 else "NS"
    prompt = (
        f"{BOLD}{gold_fg()}Coinche?{RESET}  {white_fg()}{taker_label} took the bid. "
        f"Press [C] to coinche (×2), [Enter] to accept.{RESET}"
    )
    term_w, term_h = get_term_size()
    row = max(1, term_h - 2)
    sys.stdout.write(f"\x1b[{row};1H\x1b[2K{ansi_center(prompt, term_w)}")
    sys.stdout.flush()
    invalidate_diff()
    while True:
        event = reader.read()
        if event.key in (Key.QUIT, Key.EOF, Key.ESC, Key.ENTER):
            return False
        if event.key == Key.CHAR and event.char and event.char.lower() == "c":
            return True


def prompt_surcoinche(reader: KeyReader, coincheur_label: str) -> bool:
    """4.9.0 / G1: ask SOUTH (taker team) whether to surcoinche a coinche.

    Only called when SOUTH is on the taker team and the opposing team just
    coinched. Returns True iff the player surcoinches (×4 multiplier).
    """
    prompt = (
        f"{BOLD}{gold_fg()}Surcoinche?{RESET}  {white_fg()}{coincheur_label} "
        f"coinched! Press [S] to surcoinche (×4), [Enter] to accept ×2.{RESET}"
    )
    term_w, term_h = get_term_size()
    row = max(1, term_h - 2)
    sys.stdout.write(f"\x1b[{row};1H\x1b[2K{ansi_center(prompt, term_w)}")
    sys.stdout.flush()
    invalidate_diff()
    while True:
        event = reader.read()
        if event.key in (Key.QUIT, Key.EOF, Key.ESC, Key.ENTER):
            return False
        if typed(event, "s"):  # S is also the DOWN alias — match the letter
            return True


def prompt_bid(state: GameState, reader: KeyReader) -> Suit | str | ExtensionKey | None:
    """Interactive bid selection. Returns 'QUIT' if QUIT is pressed.

    Round 2 offers Tout Atout (TA, quick-key X) and Sans Atout (SA, quick-key
    N) in addition to the three remaining card suits. Per FFBelote rules,
    round 1 is "take the up-card suit at the standard contract" only — TA/SA
    aren't offered there. 4.5.0 moved the TA/SA quick keys off `a`/`s`
    because those are now WASD nav aliases at the reader layer.

    The selector UI is painted by render() (via display(..., bid_selection=sel))
    so each frame is a single in-place repaint. Writing additional lines after
    display() would scroll the alt-screen on stricter terminals (Konsole) and
    leak previous frames onto blank padding rows.
    """
    from ..game import legal_bids

    options = legal_bids(state)

    sel = 0

    while True:
        display(state, None, bid_selection=sel)

        event = reader.read()
        if event.key in _EXTENSION_KEYS:
            return ExtensionKey(event.key)
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
            case Key.HELP | Key.THEME | Key.HIST:
                _open_overlay(event.key, state, reader)
            case Key.CHAR if event.char:
                bid = _bid_quick_key(event.char.lower(), options)
                if not isinstance(bid, _NoBidKey):
                    return bid


def _help_sections() -> list[tuple[str, list[tuple[str, str]]]]:
    """Shortcut reference, with the player's current key bindings (4.11.0)."""
    k = key_label
    move = "/".join(k(a) for a in ("up", "left", "down", "right"))
    return [
        (
            "General",
            [
                (k("help"), "This help screen"),
                (k("quit"), "Quit to menu / exit"),
                (k("theme"), "Cycle theme"),
                ("Esc", "Cancel / back"),
                (k("history"), "Round history"),
            ],
        ),
        (
            "Playing",
            [
                (f"←↑→↓ {move}", "Move selection"),
                ("Enter", "Play / confirm"),
                ("1-8", "Play that card"),
                (k("sort"), "Sort hand"),
                ("Space", "Skip animations"),
                (k("undo"), "Undo last move"),
            ],
        ),
        (
            "Bidding",
            [
                ("P", "Pass"),
                ("1-4", "Take / bid that option"),
                ("X", "Tout Atout (round 2)"),
                ("N", "Sans Atout (round 2)"),
                ("C", "Coinche (×2)"),
                ("S", "Surcoinche (×4)"),
            ],
        ),
    ]


def _help_block(title: str, rows: list[tuple[str, str]], key_w: int) -> list[str]:
    block = [f"{BOLD}{white_fg()}{title}{RESET}"]
    block += [f"  {gold_fg()}{key.ljust(key_w)}{RESET} {desc}" for key, desc in rows]
    return block


def show_help(reader: KeyReader) -> None:
    """Display a quick keyboard shortcut reference.

    4.11.0: keys are aligned in one column (each line used to be centred on
    its own, so the column zig-zagged), the sections sit side by side when the
    terminal is short (the title used to scroll off at 80×24), and the keys
    shown are the player's own bindings (Settings → Controls)."""
    term_w, term_h = get_term_size()
    sections = _help_sections()
    key_w = max(len(key) for _, rows in sections for key, _ in rows)
    blocks = [_help_block(t, rows, key_w) for t, rows in sections]
    block_w = max(visible_len(line) for b in blocks for line in b) + 2

    single = [line for b in blocks for line in [*b, ""]][:-1]
    if len(single) + 4 <= term_h or term_w < 2 * block_w + 2:
        body = single
    else:  # two columns: General + Playing | Bidding
        left = [*blocks[0], "", *blocks[1]]
        right = blocks[2]
        body = [
            ansi_ljust(left[i] if i < len(left) else "", block_w)
            + (right[i] if i < len(right) else "")
            for i in range(max(len(left), len(right)))
        ]
    body_w = max(visible_len(line) for line in body)
    pad = " " * max(0, (term_w - body_w) // 2)
    lines = [
        ansi_center(f"{BOLD}{gold_fg()}KEYBOARD SHORTCUTS{RESET}", term_w),
        "",
        *(pad + line for line in body),
        "",
        ansi_center(f"{DIM}Press any key to return{RESET}", term_w),
    ]
    top = max(0, (term_h - len(lines)) // 2)
    out = clear_screen() + hide_cursor() + "\r\n" * top
    sys.stdout.write(out + "\r\n".join(lines[: max(1, term_h - top)]))
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
        lines.append(
            f"{BOLD}{white_fg()}{'RD':<3} {'TAKER':<7} {'CON':<8} {'TRICKS':<7} STATUS{RESET}"
        )
        lines.append("─" * 40)
        for i, rs in enumerate(state.score_history):
            rd = f"{i + 1:02d}"
            taker = _hist_taker_label(rs)
            contract = _hist_contract_label(rs)
            tricks = f"{rs.tricks_ns}/{rs.tricks_ew}"
            status = _hist_status(rs)
            lines.append(f"{rd:<3} {_ljust_visible(taker, 7)} {contract:<8} {tricks:<7} {status}")
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
