"""BelAtro-specific game-history overlay (the [H] key).

Classic Belote's overlay (``belote.ui.prompts.show_history``) reads
``state.score_history``, but the BelAtro round driver never populates it:
``drive_round`` emits ``RoundEndEvent`` and calls
``ui_callbacks.on_round_end(breakdown)``, while
``apply_round_score`` — the sole writer of ``score_history`` — is only
reached from the classic ``gameflow.run_round`` path. To give [H] a
useful meaning in BelAtro we keep a parallel per-blind ledger on
``BelAtroRun.history`` and render it through this module instead.

A "round" in this overlay = one Belote deal (= one BelAtro blind). Each
entry captures the ante / blind / target / boss context that the classic
overlay has no concept of, plus the BelAtro score, status, and money
delta for the blind.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ...ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    green_fg,
    hide_cursor,
    red_fg,
    visible_len,
    white_fg,
)
from ...input import Key, KeyReader
from ...ui.render import get_term_size


@dataclass(frozen=True, slots=True)
class BelAtroHistoryEntry:
    """One row in the BelAtro [H] overlay — appended at the end of `_play_blind`."""

    ante: int                            # 1..8 (or 9+ in endless)
    blind_label: str                     # "Small" | "Big" | "Boss"
    target: int                          # blind target the player needed to reach
    boss_name: str | None                # boss name when active, else None
    taker_label: str                     # "S (NS)" / "E (EW)" / "—"
    contract: str                        # "♥" / "♣" / "♦" / "♠" / "SA" / "TA" / "—"
    tricks_ns: int
    tricks_ew: int
    score: int                           # acc.get_total(final_state) at round end
    status: str                          # "WON" | "FAILED" | "CAPOT" | "SURVIVED"
    money_delta: int                     # economy.money change across the blind
    decl_summary_ns: tuple[str, ...]
    decl_summary_ew: tuple[str, ...]


def _ljust_visible(s: str, width: int) -> str:
    pad = max(0, width - visible_len(s))
    return s + " " * pad


def _decl_str(items: tuple[str, ...], width: int) -> str:
    if not items:
        return "─"
    s = " ".join(items)
    if visible_len(s) > width:
        s = s[: max(0, width - 1)] + "…"
    return s


def _status_cell(status: str) -> str:
    if status == "CAPOT":
        return f"{gold_fg()}CAPOT{RESET}"
    if status == "FAILED":
        return f"{red_fg()}FAILED{RESET}"
    if status == "SURVIVED":
        return f"{DIM}SURVIVED{RESET}"
    if status == "WON":
        return f"{green_fg()}WON{RESET}"
    return status or "—"


def _money_cell(delta: int) -> str:
    if delta > 0:
        return f"{green_fg()}+${delta}{RESET}"
    if delta < 0:
        return f"{red_fg()}-${abs(delta)}{RESET}"
    return f"{DIM}$0{RESET}"


def show_belatro_history(reader: KeyReader, entries: list[BelAtroHistoryEntry]) -> None:
    """Scrollable BelAtro round-by-round overlay; called via the [H] hook."""
    from belote.ui.fit_guard import require_minimum

    scroll = 0

    while True:
        require_minimum(reader)
        term_w, term_h = get_term_size()

        lines: list[str] = []
        lines.append(f"{BOLD}{gold_fg()}BELATRO RUN HISTORY{RESET}")
        lines.append("=" * 19)
        lines.append("")

        if not entries:
            lines.append(f"{DIM}No blinds completed yet.{RESET}")
        else:
            # Wide layout: single-row record. ~84 visible chars at minimum.
            wide = term_w >= 90
            if wide:
                w_no, w_ante, w_bl, w_tgt, w_boss, w_tkr, w_con, w_trk, w_score, w_st, w_money = (
                    3, 4, 5, 5, 14, 7, 4, 7, 7, 8, 6,
                )
                header_cells = [
                    _ljust_visible("#", w_no),
                    _ljust_visible("ANTE", w_ante),
                    _ljust_visible("BLIND", w_bl),
                    _ljust_visible("TGT", w_tgt),
                    _ljust_visible("BOSS", w_boss),
                    _ljust_visible("TAKER", w_tkr),
                    _ljust_visible("CON", w_con),
                    _ljust_visible("TRICKS", w_trk),
                    _ljust_visible("SCORE", w_score),
                    _ljust_visible("STATUS", w_st),
                    _ljust_visible("$Δ", w_money),
                ]
                header = " │ ".join(header_cells)
                lines.append(f"{BOLD}{white_fg()}{header}{RESET}")
                lines.append("─" * visible_len(header))

                for i, e in enumerate(entries):
                    boss = e.boss_name or "─"
                    if visible_len(boss) > w_boss:
                        boss = boss[: w_boss - 1] + "…"
                    row_cells = [
                        _ljust_visible(f"{i + 1:02d}", w_no),
                        _ljust_visible(str(e.ante), w_ante),
                        _ljust_visible(e.blind_label, w_bl),
                        _ljust_visible(str(e.target), w_tgt),
                        _ljust_visible(boss, w_boss),
                        _ljust_visible(e.taker_label, w_tkr),
                        _ljust_visible(e.contract, w_con),
                        _ljust_visible(f"{e.tricks_ns}/{e.tricks_ew}", w_trk),
                        _ljust_visible(f"{BOLD}{e.score}{RESET}", w_score),
                        _ljust_visible(_status_cell(e.status), w_st),
                        _ljust_visible(_money_cell(e.money_delta), w_money),
                    ]
                    lines.append(" │ ".join(row_cells))
            else:
                # Compact three-line-per-row layout for narrow terminals.
                lines.append(
                    f"{BOLD}{white_fg()}{'#':<3} {'A.B':<4} {'TGT':<5} "
                    f"{'SCORE':<7} STATUS{RESET}"
                )
                lines.append("─" * 40)
                for i, e in enumerate(entries):
                    a_b = f"{e.ante}.{e.blind_label[0]}"
                    lines.append(
                        f"{i + 1:02d}  {a_b:<4} {e.target:<5} "
                        f"{BOLD}{e.score:<7}{RESET}{_status_cell(e.status)}"
                    )
                    boss = e.boss_name or "─"
                    lines.append(
                        f"     boss: {boss}  taker: {e.taker_label}  con: {e.contract}  "
                        f"tricks: {e.tricks_ns}/{e.tricks_ew}  {_money_cell(e.money_delta)}"
                    )
                    decl_n = _decl_str(e.decl_summary_ns, 14)
                    decl_e = _decl_str(e.decl_summary_ew, 14)
                    lines.append(f"     decl: {decl_n} / {decl_e}")
                    lines.append("")

        lines.append("")
        lines.append(f"{DIM}[↑↓] Scroll  [Any Key] Return{RESET}")

        view_h = max(1, term_h - 4)
        max_scroll = max(0, len(lines) - view_h)
        scroll = max(0, min(scroll, max_scroll))
        visible = lines[scroll : scroll + view_h]

        out = clear_screen() + hide_cursor()
        rendered = "\r\n".join(ansi_center(line, term_w) for line in visible)
        sys.stdout.write(out + rendered)
        sys.stdout.flush()

        event = reader.read()
        match event.key:
            case Key.UP:
                scroll = max(0, scroll - 1)
            case Key.DOWN:
                scroll = min(max_scroll, scroll + 1)
            case _:
                return
