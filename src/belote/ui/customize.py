"""Customisation screens reached from Settings (4.11.0).

* card back / table frame pickers with a live preview — only unlocked items
  can be chosen; locked ones are dimmed with their unlock condition;
* Controls — rebind the single-letter action keys (`input.BINDINGS`);
* Theme files — export the active theme / import one from the themes folder.

Also the Statistics screen's "Unlocks" section (`unlock_lines`). Every screen
paints with `clear_screen()` and calls `invalidate_diff()` on exit.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .. import cosmetics
from .. import settings as settings_mod
from ..ansi import (
    BOLD,
    DIM,
    RESET,
    REVERSE,
    UNDERLINE,
    ansi_center,
    ansi_ljust,
    clear_screen,
    gold_fg,
    green_fg,
    hide_cursor,
    red_fg,
)
from ..cosmetics import CardBack, Cosmetic, TableFrame
from ..input import (
    BINDINGS,
    DEFAULT_BINDINGS,
    RESERVED_KEYS,
    Key,
    KeyEvent,
    KeyReader,
    check_binding,
    raw_capture,
)
from ..settings import Settings
from ..stats import Statistics, load_stats
from ..themes import (
    THEMES,
    ThemeFileError,
    export_theme,
    import_theme,
    list_theme_files,
    theme_files_dir,
    theme_manager,
)
from .cards import card_back_chip, card_back_lines
from .layout import COMPACT, STANDARD, vcenter_lines
from .render import get_term_size, invalidate_diff
from .table import frame_preview

# ── shared helpers ──────────────────────────────────────────────────────────


def condition_text(item: Cosmetic, stats: Statistics, *, named: bool = True) -> str:
    """Unlock condition with progress: "Joueur Patient — Play 25 games. 12/25"
    (without the milestone name when `named` is False)."""
    if item.milestone is None:
        return "Free"
    m = cosmetics.MILESTONES[item.milestone]
    prog = cosmetics.progress_of(m, stats)
    tail = "(unavailable)" if prog is None else f"{prog[0]}/{prog[1]}"
    return f"{m.name} — {m.description} {tail}" if named else f"{m.description} {tail}"


def _paint(lines: list[str], rows: list[str] | None = None) -> None:
    """Paint a centred screen; `rows` are the labels of its selectable rows,
    recorded as full-row click targets (5.0.0 mouse, namespace "menu")."""
    from . import hitmap

    term_w, term_h = get_term_size()
    body = vcenter_lines([ansi_center(line, term_w) for line in lines], term_h)
    sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(body))
    sys.stdout.flush()
    if rows is not None:
        hitmap.targets_from_lines("menu", body, [(r, i) for i, r in enumerate(rows)], full_row=True)


def _click(event: KeyEvent, selected: int) -> tuple[int, Key | None]:
    """5.0.0: a click on another row selects it (no key); on the selected
    row it acts like Enter. Non-click events pass their key through."""
    from . import hitmap

    if event.key != Key.MOUSE:
        return selected, event.key
    sel, act = hitmap.select_or_act(hitmap.hit("menu", event.pos), selected)
    return sel, (Key.ENTER if act else None)


def _message_line(message: str, ok: bool) -> str:
    if not message:
        return ""
    return f"{green_fg() if ok else red_fg()}{message}{RESET}"


def chips(back_id: str, n: int = 4) -> str:
    return " ".join(card_back_chip(back_id) for _ in range(n))


def back_preview(back_id: str, *, compact: bool = False) -> list[str]:
    """A full face-down card plus opponent-hand chips in `back_id`."""
    card = card_back_lines(COMPACT if compact else STANDARD, back_id)
    return [*card, "", chips(back_id)]


def frame_sample(frame_id: str, *, compact: bool = False) -> list[str]:
    return frame_preview(
        cosmetics.table_frame(frame_id), 24 if compact else 30, 5 if compact else 6
    )


# ── Statistics: unlock list ─────────────────────────────────────────────────


def unlock_lines(stats: Statistics, fresh: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Every back and frame with ✓ or its progress; `fresh` keys get NEW."""
    earned = cosmetics.load_unlocked()
    items = list(cosmetics.all_items())
    got = sum(1 for i in items if cosmetics.is_unlocked(i, earned))
    lines = [f"  {UNDERLINE}Unlocks: {got}/{len(items)}{RESET}"]
    for title, group in (
        ("Card backs", cosmetics.CARD_BACKS.values()),
        ("Table frames", cosmetics.TABLE_FRAMES.values()),
    ):
        lines.append(f"    {BOLD}{title}{RESET}")
        for item in group:
            if cosmetics.is_unlocked(item, earned):
                new = f" {BOLD}NEW{RESET}" if item.key in fresh else ""
                lines.append(f"      {gold_fg()}✓ {item.name}{RESET}{new}")
            else:
                cond = condition_text(item, stats, named=False)
                lines.append(f"      {DIM}· {item.name:<13} {cond}{RESET}")
    return lines


# ── card back / table frame picker ──────────────────────────────────────────


@dataclass
class _Picker:
    kind: type[CardBack] | type[TableFrame]
    items: list[Cosmetic]
    earned: set[str]
    stats: Statistics
    sel: int
    message: str = ""
    ok: bool = True

    @property
    def title(self) -> str:
        return "CARD BACK" if self.kind is CardBack else "TABLE FRAME"


def picker_lines(p: _Picker, chosen: str) -> list[str]:
    """Pure line builder: item list, the highlighted item's preview, footer."""
    lines = [f"{BOLD}{gold_fg()}{p.title}{RESET}", "=" * len(p.title), ""]
    for i, item in enumerate(p.items):
        mark = "●" if item.id == chosen else " "
        if cosmetics.is_unlocked(item, p.earned):
            text = f"{mark} {item.name:<14} {item.blurb}"
            row = ansi_ljust(text, 66)
            lines.append(f"{REVERSE} {row} {RESET}" if i == p.sel else f" {row} ")
        else:
            cond = condition_text(item, p.stats, named=False)
            text = ansi_ljust(f"  {item.name:<14} {cond}", 66)
            lines.append(
                f"{REVERSE}{DIM} {text} {RESET}" if i == p.sel else f"{DIM} {text} {RESET}"
            )
    lines.append("")
    item = p.items[p.sel]
    lines += back_preview(item.id) if p.kind is CardBack else frame_sample(item.id)
    if cosmetics.is_unlocked(item, p.earned):
        lines.append(f"{gold_fg()}{item.name}{RESET}")
    else:
        lines.append(f"{DIM}{item.name} · locked · {condition_text(item, p.stats)}{RESET}")
    lines += ["", _message_line(p.message, p.ok)]
    lines.append(f"{DIM}↑/↓ preview   Enter: choose   Esc: back{RESET}")
    return lines


def _choose(p: _Picker, s: Settings) -> None:
    item = p.items[p.sel]
    if not cosmetics.is_unlocked(item, p.earned):
        p.message, p.ok = f"Locked — {condition_text(item, p.stats)}", False
        return
    if p.kind is CardBack:
        s.card_back = item.id
    else:
        s.table_frame = item.id
    settings_mod.apply(s)
    p.message, p.ok = f"{item.name} selected", True


def show_cosmetic_picker(
    reader: KeyReader, s: Settings, kind: type[CardBack] | type[TableFrame]
) -> None:
    """Pick the card back (``CardBack``) or table frame (``TableFrame``)."""
    fresh = cosmetics.check_unlocks()
    registry: dict[str, CardBack] | dict[str, TableFrame] = (
        cosmetics.CARD_BACKS if kind is CardBack else cosmetics.TABLE_FRAMES
    )
    items: list[Cosmetic] = list(registry.values())
    chosen = s.card_back if kind is CardBack else s.table_frame
    ids = [i.id for i in items]
    p = _Picker(
        kind,
        items,
        cosmetics.load_unlocked(),
        load_stats(),
        ids.index(chosen) if chosen in ids else 0,
    )
    if fresh:
        p.message = "Unlocked: " + ", ".join(u.item.name for u in fresh)
    try:
        while True:
            _paint(
                picker_lines(p, s.card_back if kind is CardBack else s.table_frame),
                [item.name for item in items],
            )
            event = reader.read()
            before = p.sel
            p.sel, key = _click(event, p.sel)
            if p.sel != before:
                p.message = ""
            if key in (Key.ESC, Key.QUIT, Key.EOF):
                return
            if key in (Key.UP, Key.LEFT):
                p.sel, p.message = (p.sel - 1) % len(items), ""
            elif key in (Key.DOWN, Key.RIGHT):
                p.sel, p.message = (p.sel + 1) % len(items), ""
            elif key == Key.ENTER:
                _choose(p, s)
    finally:
        invalidate_diff()


# ── Controls ────────────────────────────────────────────────────────────────


def _full_bindings(s: Settings) -> dict[str, str]:
    return {**DEFAULT_BINDINGS, **s.keys}


def controls_lines(s: Settings, sel: int, message: str = "", ok: bool = True) -> list[str]:
    """Pure line builder for the Controls screen."""
    current = _full_bindings(s)
    lines = [f"{BOLD}{gold_fg()}CONTROLS{RESET}", "========", ""]
    labels = [(b.label, current[b.action].upper()) for b in BINDINGS]
    labels += [("Reset to defaults", ""), ("Back", "")]
    for i, (label, key) in enumerate(labels):
        changed = i < len(BINDINGS) and key.lower() != BINDINGS[i].default
        text = f"{label:<26}{key:>3}{' *' if changed else '  '}"
        lines.append(f"{REVERSE} {text} {RESET}" if i == sel else f" {text} ")
    reserved = " ".join(k.upper() for k in sorted(RESERVED_KEYS))
    lines += [
        "",
        _message_line(message, ok),
        f"{DIM}Fixed: arrows, Enter, Esc, Space, digits. Reserved letters: {reserved}{RESET}",
        f"{DIM}↑/↓ select   Enter: rebind   Esc: back (saves){RESET}",
    ]
    return lines


def rebind(s: Settings, action: str, key: str) -> str | None:
    """Bind `action` to `key` on `s` and apply it; returns the conflict
    message instead (and changes nothing) when the key can't be used."""
    current = _full_bindings(s)
    err = check_binding(action, key, current)
    if err is not None:
        return err
    current[action] = key.lower()
    s.keys = {a: k for a, k in current.items() if k != DEFAULT_BINDINGS[a]}
    settings_mod.apply(s)
    return None


def _capture(reader: KeyReader, s: Settings, idx: int) -> tuple[str, bool]:
    """Read the new key for binding `idx`; returns (message, ok)."""
    b = BINDINGS[idx]
    _paint(controls_lines(s, idx, f"Press the new key for {b.label}  (Esc cancels)", True))
    with raw_capture():
        event = reader.read()
    if event.key in (Key.ESC, Key.EOF, Key.QUIT):
        return "Cancelled", True
    if event.char is None:
        return "Arrows, Enter, Esc, Tab and Space can't be bound", False
    err = rebind(s, b.action, event.char)
    if err is not None:
        return err, False
    return f"{b.label} → {event.char.upper()}", True


def show_controls(reader: KeyReader, s: Settings) -> None:
    """Interactive key rebinding. Applies live; the caller saves `s`."""
    n_rows = len(BINDINGS) + 2
    sel, message, ok = 0, "", True
    try:
        row_labels = [b.label for b in BINDINGS] + ["Reset to defaults", "Back"]
        while True:
            _paint(controls_lines(s, sel, message, ok), row_labels)
            event = reader.read()
            message = ""
            sel, key = _click(event, sel)
            if key in (Key.ESC, Key.QUIT, Key.EOF):
                return
            if key == Key.UP:
                sel = (sel - 1) % n_rows
            elif key == Key.DOWN:
                sel = (sel + 1) % n_rows
            elif key == Key.ENTER:
                if sel == n_rows - 1:
                    return
                if sel == n_rows - 2:
                    s.keys = {}
                    settings_mod.apply(s)
                    message, ok = "All keys reset to defaults", True
                else:
                    message, ok = _capture(reader, s, sel)
    finally:
        invalidate_diff()


# ── Theme files ─────────────────────────────────────────────────────────────


def theme_file_lines(files: list[str], sel: int, message: str = "", ok: bool = True) -> list[str]:
    """Pure line builder: export row, one import row per file, Back."""
    current = theme_manager.get_current().name
    lines = [
        f"{BOLD}{gold_fg()}THEME FILES{RESET}",
        "===========",
        f"{DIM}Folder: {theme_files_dir()}{RESET}",
        "",
    ]
    rows = [f"Export current theme ({current})", *(f"Import  {f}" for f in files), "Back"]
    for i, text in enumerate(rows):
        lines.append(f"{REVERSE} {text} {RESET}" if i == sel else f" {text} ")
        if i == 0 and not files:
            lines.append(f"{DIM}  (no theme files to import yet){RESET}")
    lines += [
        "",
        _message_line(message, ok),
        f"{DIM}↑/↓ select   Enter: export / import   Esc: back{RESET}",
    ]
    return lines


def export_current() -> tuple[str, bool]:
    try:
        path = export_theme(theme_manager.current_name)
    except OSError as e:
        return f"Export failed: {e.strerror or 'file error'}", False
    return f"Exported to {path.name}", True


def import_file(name: str) -> tuple[str, bool]:
    """Import and activate theme file `name` from the themes folder."""
    try:
        key = import_theme(theme_files_dir() / name)
    except ThemeFileError as e:
        return f"Can't import {name}: {e}", False
    theme_manager.set_current(key)
    return f"Imported “{THEMES[key].name}” — now active", True


def show_theme_files(reader: KeyReader) -> None:
    """Export the active theme or import one from the themes folder."""
    sel, message, ok = 0, "", True
    try:
        while True:
            files = [p.name for p in list_theme_files()]
            n_rows = len(files) + 2
            sel = min(sel, n_rows - 1)
            labels = ["Export current theme", *(f"Import  {f}" for f in files), "Back"]
            _paint(theme_file_lines(files, sel, message, ok), labels)
            event = reader.read()
            sel, key = _click(event, sel)
            if key in (Key.ESC, Key.QUIT, Key.EOF):
                return
            if key == Key.UP:
                sel = (sel - 1) % n_rows
            elif key == Key.DOWN:
                sel = (sel + 1) % n_rows
            elif key == Key.ENTER:
                if sel == n_rows - 1:
                    return
                message, ok = export_current() if sel == 0 else import_file(files[sel - 1])
    finally:
        invalidate_diff()
