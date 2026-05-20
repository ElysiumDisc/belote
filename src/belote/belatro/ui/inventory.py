"""Inventory overlay (4.7.0) — V key.

A detail-on-select pager listing every owned item across the BelAtro run:
jokers (with edition), vouchers, consumables (tarots / planets), the
permanent chip / mult bonuses accrued from tarots, and the per-contract
planet levels. Mirrors `ConsumablesOverlay`'s alt-screen-safe paint
pattern (clear_screen + vcenter_lines + invalidate_diff in finally),
but adds a two-view state machine: a navigable list + an Enter-driven
per-item detail page.

Wired from `belote/ui/prompts.py::prompt_card` via the new `Key.INVENTORY`
enum value (V key), with the `belatro/main.py::UICallbacks._show_inventory`
shim. The C key's `ConsumablesOverlay` continues to serve the
"activate a tarot/planet" flow separately — V is read-only, C is action.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from belote.ansi import (
    BOLD,
    DIM,
    RESET,
    ansi_center,
    clear_screen,
    gold_fg,
    green_fg,
    white_fg,
)
from belote.input import Key

if TYPE_CHECKING:
    from belote.input import KeyReader

    from ..core.run_state import BelAtroRun


@dataclass(frozen=True, slots=True)
class _InventoryEntry:
    """A single navigable row in the inventory list.

    `category` groups entries under section headers (rendered as DIM rows
    in the list view). `detail_lines` is the body of the detail page,
    shown when the player hits Enter on this row. `title` is what the
    list view displays.
    """

    category: str
    title: str
    detail_lines: tuple[str, ...]


_CATEGORY_ORDER: tuple[str, ...] = (
    "JOKERS",
    "VOUCHERS",
    "CONSUMABLES",
    "PERMANENT BONUSES",
    "CONTRACT LEVELS",
)


def _edition_tag(item: object) -> str:
    """Return a `[Foil]` / `[Holo]` / `[Polychrome]` / `[Negative]` suffix
    for a joker (or empty string for non-edition items). Reads the
    `edition` attribute defensively — tarots, vouchers, and planets don't
    carry editions today and the attribute is absent on them."""
    edition = getattr(item, "edition", None)
    if edition is None:
        return ""
    name = getattr(edition, "name", str(edition)).lower()
    if name in ("none", ""):
        return ""
    return f" [{name.capitalize()}]"


def _build_entries(run: BelAtroRun) -> list[_InventoryEntry]:
    """Flatten owned items into a list of `_InventoryEntry` rows.

    Snapshot-stable — taken once when the overlay opens so live mutations
    (a joker discarded mid-overlay) don't shift selection.
    """
    entries: list[_InventoryEntry] = []

    # Jokers — name + edition tag + description; detail page surfaces the
    # description plus the edition's per-trigger bonus when present.
    for joker in run.jokers:
        name = getattr(joker, "name", "?")
        desc = getattr(joker, "description", "")
        title = f"{name}{_edition_tag(joker)}"
        detail = [desc] if desc else []
        edition = getattr(joker, "edition", None)
        if edition is not None:
            edition_name = getattr(edition, "name", "").lower()
            if edition_name == "foil":
                detail.append("")
                detail.append("Edition: Foil — +50 chips per trigger")
            elif edition_name == "holo":
                detail.append("")
                detail.append("Edition: Holo — +10 Mult per trigger")
            elif edition_name in ("polychrome", "poly"):
                detail.append("")
                detail.append("Edition: Polychrome — ×1.5 Mult per trigger")
            elif edition_name in ("negative", "neg"):
                detail.append("")
                detail.append("Edition: Negative — does not consume a joker slot")
        entries.append(
            _InventoryEntry(
                category="JOKERS",
                title=title,
                detail_lines=tuple(detail),
            )
        )

    # Vouchers
    for voucher in run.vouchers:
        name = getattr(voucher, "name", "?")
        desc = getattr(voucher, "description", "")
        entries.append(
            _InventoryEntry(
                category="VOUCHERS",
                title=name,
                detail_lines=(desc,) if desc else (),
            )
        )

    # Consumables — tarots and planets held but not yet activated. Press C
    # in the shop to use these; V here is read-only.
    for consumable in run.consumables:
        name = getattr(consumable, "name", "?")
        desc = getattr(consumable, "description", "")
        kind = type(consumable).__name__
        title = f"{name} ({kind})"
        entries.append(
            _InventoryEntry(
                category="CONSUMABLES",
                title=title,
                detail_lines=(desc,) if desc else (),
            )
        )

    # Permanent bonuses — single composite row when non-default values exist.
    perm_chips = run.permanent_chips
    perm_mult = run.permanent_mult
    if perm_chips != 0 or perm_mult != 1.0:
        bits: list[str] = []
        if perm_chips:
            bits.append(f"+{perm_chips} chips")
        if perm_mult != 1.0:
            bits.append(f"×{perm_mult:.2f} Mult")
        entries.append(
            _InventoryEntry(
                category="PERMANENT BONUSES",
                title=" · ".join(bits),
                detail_lines=(
                    "These bonuses are seeded into the ledger at the start "
                    "of every round (see `ScoreAccumulator.trigger_round_start`).",
                    "Accrued from L'Étoile / Le Monde / planet level-ups.",
                ),
            )
        )

    # Contract levels — each leveled planet shows up here.
    for contract_id, reward in run.contract_levels.items():
        if not reward:
            continue
        reward_bits: list[str] = []
        if reward.get("add_chips"):
            reward_bits.append(f"+{reward['add_chips']} chips/trick")
        if reward.get("add_mult"):
            reward_bits.append(f"+{reward['add_mult']} Mult/trick")
        if reward.get("jack_9_bonus"):
            reward_bits.append(f"+{reward['jack_9_bonus']} chips per J/9")
        if reward.get("honor_bonus"):
            reward_bits.append(f"+{reward['honor_bonus']} chips per honor")
        if reward.get("bonus_mult_per_trick"):
            reward_bits.append(f"+{reward['bonus_mult_per_trick']} Mult per trick >4")
        if reward.get("add_money"):
            reward_bits.append(f"+${reward['add_money']} at round end")
        if reward.get("capot_bonus"):
            reward_bits.append(f"+{reward['capot_bonus']} chips on capot")
        if reward.get("coinche_multiplier"):
            reward_bits.append(f"+{reward['coinche_multiplier']} Mult per coinche")
        detail_body = "; ".join(reward_bits) if reward_bits else "(no leveled effects)"
        entries.append(
            _InventoryEntry(
                category="CONTRACT LEVELS",
                title=f"{contract_id}",
                detail_lines=(detail_body,),
            )
        )

    return entries


class InventoryOverlay:
    """V-key overlay showing the player's owned items in detail."""

    def __init__(self, run: BelAtroRun, reader: KeyReader) -> None:
        self.run = run
        self.reader = reader

    def open(self) -> None:
        """Show the overlay until the player closes it.

        State machine: list view ↔ detail view. Both views call
        `invalidate_diff()` on exit via the `finally` block so the next
        `display()` call repaints the full game state (mirrors the 4.6.4
        overlay discipline pinned by
        `tests/test_alt_screen_scroll.py::test_belatro_overlays_invalidate_diff`).
        """
        from belote.ui.fit_guard import require_minimum
        from belote.ui.render import invalidate_diff

        require_minimum(self.reader)
        entries = _build_entries(self.run)

        try:
            if not entries:
                self._render_empty()
                self._wait_for_close()
                return

            selected = 0
            while True:
                self._render_list(entries, selected)
                event = self.reader.read()
                if event.key in (Key.ESC, Key.QUIT, Key.EOF, Key.INVENTORY):
                    return
                if event.key in (Key.UP, Key.LEFT):
                    selected = (selected - 1) % len(entries)
                elif event.key in (Key.DOWN, Key.RIGHT):
                    selected = (selected + 1) % len(entries)
                elif event.key == Key.ENTER:
                    # Detail view loop. ESC / ← / V pop back to the list;
                    # ENTER on detail does nothing (no further drill-down).
                    while True:
                        self._render_detail(entries[selected])
                        de = self.reader.read()
                        if de.key in (
                            Key.ESC, Key.QUIT, Key.EOF,
                            Key.LEFT, Key.INVENTORY,
                        ):
                            break
        finally:
            invalidate_diff()

    # ── rendering ────────────────────────────────────────────────────────

    def _term(self) -> tuple[int, int]:
        from belote.ui.render import get_term_size
        w, h = get_term_size()
        return w, h

    def _render_empty(self) -> None:
        from belote.ui.layout import vcenter_lines
        term_w, term_h = self._term()
        lines = [
            ansi_center(gold_fg() + BOLD + "INVENTORY" + RESET, term_w),
            "",
            ansi_center(
                white_fg() + "(no items owned — buy from the shop)" + RESET,
                term_w,
            ),
            "",
            ansi_center(DIM + "Press any key to return" + RESET, term_w),
        ]
        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()

    def _wait_for_close(self) -> None:
        while True:
            event = self.reader.read()
            if event.key in (
                Key.ESC, Key.QUIT, Key.ENTER, Key.EOF, Key.INVENTORY,
            ):
                return

    def _render_list(
        self, entries: list[_InventoryEntry], selected: int
    ) -> None:
        from belote.ui.layout import vcenter_lines
        term_w, term_h = self._term()
        joker_count = sum(1 for e in entries if e.category == "JOKERS")
        header = (
            f"INVENTORY  ·  Ante {self.run.ante_number}/8  ·  "
            f"Jokers {joker_count}/{self.run.joker_slots}"
        )
        lines: list[str] = [
            ansi_center(gold_fg() + BOLD + header + RESET, term_w),
            "",
        ]

        # Group entries by category preserving _CATEGORY_ORDER.
        current_category: str | None = None
        for i, entry in enumerate(entries):
            if entry.category != current_category:
                if current_category is not None:
                    lines.append("")  # blank line between sections
                lines.append(
                    ansi_center(
                        green_fg() + BOLD + f"── {entry.category} ──" + RESET,
                        term_w,
                    )
                )
                current_category = entry.category
            marker = "▶" if i == selected else " "
            tint = gold_fg() + BOLD if i == selected else white_fg()
            lines.append(ansi_center(tint + f"{marker} {entry.title}" + RESET, term_w))

        lines.append("")
        lines.append(
            ansi_center(
                DIM + "[↑/↓] move   [Enter] detail   [Esc/V/Q] close" + RESET,
                term_w,
            )
        )

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()

    def _render_detail(self, entry: _InventoryEntry) -> None:
        from belote.ui.layout import vcenter_lines
        term_w, term_h = self._term()
        lines: list[str] = [
            ansi_center(
                green_fg() + BOLD + f"── {entry.category} ──" + RESET, term_w
            ),
            "",
            ansi_center(gold_fg() + BOLD + entry.title + RESET, term_w),
            "",
        ]
        for body_line in entry.detail_lines:
            lines.append(ansi_center(white_fg() + body_line + RESET, term_w))
        if not entry.detail_lines:
            lines.append(ansi_center(DIM + "(no description)" + RESET, term_w))
        lines.append("")
        lines.append(
            ansi_center(DIM + "[Esc/←/V] back to list" + RESET, term_w)
        )

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()
