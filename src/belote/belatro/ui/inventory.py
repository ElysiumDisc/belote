"""Inventory overlay (4.7.0; 4.9.0 / U5 — activation merged in) — V key.

A detail-on-select pager listing every owned item across the BelAtro run:
jokers (with edition), vouchers, consumables (tarots / planets), the
permanent chip / mult bonuses accrued from tarots, and the per-contract
planet levels. Mirrors `ConsumablesOverlay`'s alt-screen-safe paint
pattern (clear_screen + vcenter_lines + invalidate_diff in finally),
but adds a two-view state machine: a navigable list + an Enter-driven
per-item detail page.

4.9.0 / U5: V is no longer purely read-only. Pressing `1`–`9` activates
the Nth consumable directly from the list; pressing `A` on a consumable's
detail page does the same. The shop's `C` key still launches the
numbered `ConsumablesOverlay` for that quick-pick flow (the two coexist:
V is the unified screen, C is the in-shop quick path).

Wired from `belote/ui/prompts.py::prompt_card` via the `Key.INVENTORY`
enum value (V key), with the `belatro/main.py::UICallbacks._show_inventory`
shim.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
from belote.input import Key, key_label, typed

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

    4.9.0 / U5: `consumable_idx` is set for CONSUMABLES rows to the row's
    index in `run.consumables`. None for non-consumable rows. Lets the
    activation handler bypass a separate snapshot.
    """

    category: str
    title: str
    detail_lines: tuple[str, ...]
    consumable_idx: int | None = None


_CATEGORY_ORDER: tuple[str, ...] = (
    "JOKERS",
    "PARTNER JOKERS",
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


# Edition → the detail-page line describing its per-trigger bonus.
_EDITION_DETAIL: dict[str, str] = {
    "foil": "Edition: Foil — +50 chips per trigger",
    "holo": "Edition: Holo — +10 Mult per trigger",
    "polychrome": "Edition: Polychrome — ×1.5 Mult per trigger",
    "poly": "Edition: Polychrome — ×1.5 Mult per trigger",
    "negative": "Edition: Negative — does not consume a joker slot",
    "neg": "Edition: Negative — does not consume a joker slot",
}

# Contract-level reward keys, in display order, with their formats.
_REWARD_FORMATS: tuple[tuple[str, str], ...] = (
    ("add_chips", "+{} chips/trick"),
    ("add_mult", "+{} Mult/trick"),
    ("jack_9_bonus", "+{} chips per J/9"),
    ("honor_bonus", "+{} chips per honor"),
    ("bonus_mult_per_trick", "+{} Mult per trick >4"),
    ("add_money", "+${} at round end"),
    ("capot_bonus", "+{} chips on capot"),
    ("coinche_multiplier", "+{} Mult per coinche"),
    ("last_trick_chips", "+{} chips on Dix de Der"),
)


def _joker_entry(joker: object) -> _InventoryEntry:
    """Name + edition tag; the detail page adds the edition's bonus."""
    desc = getattr(joker, "description", "")
    detail = [desc] if desc else []
    edition = getattr(joker, "edition", None)
    if edition is not None:
        line = _EDITION_DETAIL.get(getattr(edition, "name", "").lower())
        if line:
            detail += ["", line]
    return _InventoryEntry(
        category="JOKERS",
        title=f"{getattr(joker, 'name', '?')}{_edition_tag(joker)}",
        detail_lines=tuple(detail),
    )


def _permanent_bonus_entry(run: BelAtroRun) -> _InventoryEntry | None:
    """One composite row, only when the bonuses differ from the defaults."""
    perm_chips = run.permanent_chips
    perm_mult = run.permanent_mult
    if perm_chips == 0 and perm_mult == 1.0:
        return None
    bits: list[str] = []
    if perm_chips:
        bits.append(f"+{perm_chips} chips")
    if perm_mult != 1.0:
        bits.append(f"×{perm_mult:.2f} Mult")
    return _InventoryEntry(
        category="PERMANENT BONUSES",
        title=" · ".join(bits),
        detail_lines=(
            "These bonuses are seeded into the ledger at the start "
            "of every round (see `ScoreAccumulator.trigger_round_start`).",
            "Accrued from L'Étoile / Le Monde / planet level-ups.",
        ),
    )


def _contract_level_entry(contract_id: str, reward: Any) -> _InventoryEntry:
    reward_bits = [fmt.format(reward[key]) for key, fmt in _REWARD_FORMATS if reward.get(key)]
    return _InventoryEntry(
        category="CONTRACT LEVELS",
        title=f"{contract_id}",
        detail_lines=("; ".join(reward_bits) if reward_bits else "(no leveled effects)",),
    )


def _build_entries(run: BelAtroRun) -> list[_InventoryEntry]:
    """Flatten owned items into a list of `_InventoryEntry` rows.

    Snapshot-stable — taken once when the overlay opens so live mutations
    (a joker discarded mid-overlay) don't shift selection.
    """
    entries = [_joker_entry(joker) for joker in run.jokers]
    # 4.11.0: jokers on the partner's own slots (Le Téléphone, Le Complice).
    entries += [
        _InventoryEntry(
            category="PARTNER JOKERS",
            title=f"{getattr(joker, 'name', '?')} (partner slot)",
            detail_lines=_joker_entry(joker).detail_lines,
        )
        for joker in run.partner.jokers
    ]
    for voucher in run.vouchers:
        desc = getattr(voucher, "description", "")
        entries.append(
            _InventoryEntry(
                category="VOUCHERS",
                title=getattr(voucher, "name", "?"),
                detail_lines=(desc,) if desc else (),
            )
        )
    # Consumables — tarots and planets held but not yet activated. 4.9.0 /
    # U5: each entry remembers its index in `run.consumables` so digit-key
    # and detail-page activation can dispatch without a second snapshot.
    for idx, consumable in enumerate(run.consumables):
        desc = getattr(consumable, "description", "")
        kind = type(consumable).__name__
        entries.append(
            _InventoryEntry(
                category="CONSUMABLES",
                title=f"[{idx + 1}] {getattr(consumable, 'name', '?')} ({kind})",
                detail_lines=(desc,) if desc else (),
                consumable_idx=idx,
            )
        )
    bonus = _permanent_bonus_entry(run)
    if bonus is not None:
        entries.append(bonus)
    # Contract levels — each leveled planet shows up here.
    entries.extend(
        _contract_level_entry(cid, reward) for cid, reward in run.contract_levels.items() if reward
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
                elif event.key == Key.CHAR and event.char and event.char.isdigit():
                    # 4.9.0 / U5: digit activates the Nth consumable directly.
                    idx = int(event.char) - 1
                    if self._activate_consumable_at(idx):
                        # Rebuild entries — `consume()` removes the item, so
                        # the indices shift. Reset selection if past the end.
                        entries = _build_entries(self.run)
                        if not entries:
                            self._render_empty()
                            self._wait_for_close()
                            return
                        selected = min(selected, len(entries) - 1)
                elif event.key == Key.ENTER:
                    # Detail view loop. ESC / ← / V pop back to the list;
                    # `A` on a consumable detail page activates it (U5).
                    detail_idx = selected
                    while True:
                        self._render_detail(entries[detail_idx])
                        de = self.reader.read()
                        # A is also the LEFT alias (= back): test the letter first.
                        if typed(de, "a"):
                            cidx = entries[detail_idx].consumable_idx
                            if cidx is not None and self._activate_consumable_at(cidx):
                                entries = _build_entries(self.run)
                                if not entries:
                                    self._render_empty()
                                    self._wait_for_close()
                                    return
                                selected = min(selected, len(entries) - 1)
                                break  # pop back to list view
                            continue
                        if de.key in (
                            Key.ESC,
                            Key.QUIT,
                            Key.EOF,
                            Key.LEFT,
                            Key.INVENTORY,
                        ):
                            break
        finally:
            invalidate_diff()

    def _activate_consumable_at(self, idx: int) -> bool:
        """Activate `run.consumables[idx]` if it exists. 4.9.0 / U5."""
        if not (0 <= idx < len(self.run.consumables)):
            return False
        item = self.run.consumables[idx]
        return self.run.consume(item, context=self.run)

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
                Key.ESC,
                Key.QUIT,
                Key.ENTER,
                Key.EOF,
                Key.INVENTORY,
            ):
                return

    def _render_list(self, entries: list[_InventoryEntry], selected: int) -> None:
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
        # 4.9.0 / U5: surface the digit-activate path when consumables exist.
        has_consumables = any(e.consumable_idx is not None for e in entries)
        close = f"Esc/{key_label('inventory')}/{key_label('quit')}"
        if has_consumables:
            footer = f"[↑/↓] move   [Enter] detail   [1-9] activate consumable   [{close}] close"
        else:
            footer = f"[↑/↓] move   [Enter] detail   [{close}] close"
        lines.append(ansi_center(DIM + footer + RESET, term_w))

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()

    def _render_detail(self, entry: _InventoryEntry) -> None:
        from belote.ui.layout import vcenter_lines

        term_w, term_h = self._term()
        lines: list[str] = [
            ansi_center(green_fg() + BOLD + f"── {entry.category} ──" + RESET, term_w),
            "",
            ansi_center(gold_fg() + BOLD + entry.title + RESET, term_w),
            "",
        ]
        for body_line in entry.detail_lines:
            lines.append(ansi_center(white_fg() + body_line + RESET, term_w))
        if not entry.detail_lines:
            lines.append(ansi_center(DIM + "(no description)" + RESET, term_w))
        lines.append("")
        # 4.9.0 / U5: show activate hint on consumable detail pages.
        if entry.consumable_idx is not None:
            lines.append(ansi_center(DIM + "[A] activate   [Esc/←/V] back to list" + RESET, term_w))
        else:
            lines.append(ansi_center(DIM + "[Esc/←/V] back to list" + RESET, term_w))

        sys.stdout.write(clear_screen() + "\r\n".join(vcenter_lines(lines, term_h)))
        sys.stdout.flush()
