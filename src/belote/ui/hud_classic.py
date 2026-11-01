"""Classic-game HUD bar and the bidding prompt lines.

Split out of `ui/render.py` in 4.11.0. BelAtro plugs a bid hint in through
`set_bid_hint_provider` (core never imports the expansion). The names stay
importable from `belote.ui.render` for compatibility.
"""

from __future__ import annotations

from collections.abc import Callable

from ..ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    ansi_center,
    ansi_ljust,
    ansi_truncate,
    banner_bg,
    banner_fg,
    black_fg,
    gold_fg,
    light_gray_fg,
    red_fg,
    visible_len,
    white_fg,
)
from ..deck import Suit
from ..game import (
    SANS_ATOUT_BID,
    GameState,
    Phase,
    Seat,
    legal_bids,
)
from ..input import key_label
from ..themes import theme_manager
from .layout import STANDARD, LayoutPreset


def _build_hud(
    state: GameState,
    term_w: int,
    layout: LayoutPreset = STANDARD,
    *,
    team_scores_override: tuple[int, int] | None = None,
) -> str:
    """Build the top HUD bar, padded to term_w visible chars.

    Verbosity is layout-driven:
      - "verbose"  (spacious): all labels, help hints, theme name
      - "standard": current behaviour (full labels, hints, theme)
      - "compact"  (≤80 cols): abbreviated labels, no help hints, no theme name

    `team_scores_override` lets the score-roll animation in announce.py paint
    intermediate frames without allocating a fresh frozen GameState per step.
    """
    if state.variants.hide_hud:
        left = f"{BOLD}{gold_fg()}BELOTE{RESET}"
        mid = f"{DIM} [HUD HIDDEN BY BOSS] {RESET}"
        if layout.hud_style == "compact":
            return ansi_ljust(left + "   " + mid, term_w)
        theme_label = f"{DIM}Theme: {theme_manager.get_current().name}{RESET}"
        return _fit_hud(left + "   " + mid, theme_label, term_w)

    trump_sym = state.trump.symbol if state.trump else "?"
    ns, ew = team_scores_override if team_scores_override is not None else state.team_scores
    trick_num = len(state.completed_tricks) + (1 if state.current_trick else 0)
    taker_name = state.taker.name if state.taker else "-"
    ns_pts, ew_pts = state.current_round_points

    left = f"{BOLD}{gold_fg()}BELOTE{RESET}"

    # 4.9.0 / G3: surface the carried-over litige pool. The pool is team-
    # neutral — it accrues across all-pass-litige rounds and is absorbed by
    # whichever team fulfills the next non-litige contract (see
    # `scoring.py::_score_normal_outcome` line ~911).
    litige_chip_compact = ""
    litige_chip_full = ""
    if state.litige_points > 0:
        litige_chip_compact = f"  {DIM}{gold_fg()}Lit:{state.litige_points}{RESET}"
        litige_chip_full = f"{DIM}{gold_fg()}Litige: {state.litige_points}{RESET}   "

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
            f"{litige_chip_compact}"
        )
        return ansi_ljust(bar, term_w)

    # Standard / verbose: full labels, hints, theme on the right.
    theme_label = f"{DIM}Theme: {theme_manager.get_current().name}{RESET}"
    core = (
        f"{left}   "
        f"{white_fg()}Trump: {trump_sym}   "
        f"NS: {BOLD}{ns}{RESET}{white_fg()} (+{ns_pts})   "
        f"EW: {BOLD}{ew}{RESET}{white_fg()} (+{ew_pts})   "
        f"{litige_chip_full}"
        f"Trick {trick_num}/8   Taker: {taker_name}"
    )
    keys = " ".join(
        f"[{key_label(action)}]{word}"
        for action, word in (
            ("history", "Hist"),
            ("theme", "Theme"),
            ("undo", "Undo"),
            ("overlay", "HUD"),
        )
    )
    bar = core + f"   {DIM}{keys}{RESET}"
    return _fit_hud(bar, theme_label, term_w, fallback=core + RESET)


def _fit_hud(bar: str, theme_label: str, term_w: int, *, fallback: str | None = None) -> str:
    """Lay out `bar` + right-aligned `theme_label` in exactly `term_w` cells.

    At 120-143 cols, 3-digit scores / the litige chip / a long theme name
    pushed the spacious HUD past term_w, so the row wrapped and the alt screen
    scrolled. Optional segments are dropped in order — theme label, then the
    key-hint tail (`bar` -> `fallback`) — and the result is finally clamped.
    """
    vlen_bar = visible_len(bar)
    vlen_theme = visible_len(theme_label)
    # Historical layout leaves the last column free (width term_w - 1); the
    # extra +1 keeps at least one space so the hints never run into "Theme:".
    if vlen_bar + vlen_theme + 2 <= term_w:
        pad = term_w - vlen_bar - vlen_theme - 1
        return bar + " " * pad + theme_label
    for cand in (bar, fallback):
        if cand is not None and visible_len(cand) <= term_w:
            return ansi_ljust(cand, term_w)
    # RESET after the cut so a truncated colour span can't bleed onward.
    clamped = ansi_truncate(fallback if fallback is not None else bar, term_w) + RESET
    return ansi_ljust(clamped, term_w)


# Optional one-line hint painted above the bid selector. Expansions install a
# provider (BelAtro shows the partner's bidding tendency); classic has none.
_bid_hint_provider: Callable[[GameState], str | None] | None = None


def set_bid_hint_provider(provider: Callable[[GameState], str | None] | None) -> None:
    global _bid_hint_provider
    _bid_hint_provider = provider


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
        round2_suits = legal_bids(state)
        labels = [
            "Pass"
            if b is None
            else "TA"
            if b == Suit.TOUT_ATOUT
            else "SA"
            if b == SANS_ATOUT_BID
            else b.symbol
            for b in round2_suits
        ]

    lines: list[str] = []

    hint = _bid_hint_provider(state) if _bid_hint_provider is not None else None
    if hint:
        lines.append(ansi_center(f"{DIM}{hint}{RESET}", term_w))

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


def _phase_info(state: GameState) -> str:
    """Whose turn it is / round complete, plus a Belote/Rebelote banner."""
    phase_info = ""
    if state.phase in (Phase.BIDDING, Phase.PLAYING):
        if state.turn == Seat.SOUTH:
            phase_info = f"{BOLD}{gold_fg()}>> YOUR TURN <<{RESET}"
        else:
            what = " to bid" if state.phase == Phase.BIDDING else ""
            phase_info = f"{light_gray_fg()}Waiting for {state.turn.name}{what}...{RESET}"
    elif state.phase == Phase.SCORING:
        phase_info = f"{BOLD}{gold_fg()}Round complete!{RESET}"

    if state.belote_tracker[1]:
        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Rebelote! {RESET}"
    elif state.belote_tracker[0]:
        phase_info += f"  {BOLD}{banner_bg()}{banner_fg()} Belote! {RESET}"
    return phase_info


def _bid_lines(state: GameState, term_w: int, bid_selection: int | None) -> list[str]:
    """SOUTH's bidding prompt: the interactive selector, or the static hint."""
    if bid_selection is not None:
        return _build_bid_prompt_lines(state, term_w, bid_selection)
    prompt = f"{BOLD}{gold_fg()}Bid: [P]ass  [1]♠  [2]♥  [3]♦  [4]♣{RESET}"
    return [ansi_center(prompt, term_w)]
