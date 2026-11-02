"""Settings screen: game setup, display/accessibility and extras.

Every change applies immediately (`settings.apply`) and is saved when the
screen closes. Rows contributed by expansions (`settings.register_toggle`)
appear after the core rows. 4.11.0: card back / table frame pickers (with a
live preview), Controls and theme files open the screens in `ui/customize.py`.
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
    ansi_center,
    ansi_ljust,
    ansi_truncate,
    clear_screen,
    gold_fg,
    hide_cursor,
    visible_len,
)
from ..cosmetics import CardBack, TableFrame
from ..game import Seat
from ..input import Key, KeyEvent, KeyReader
from ..settings import DIFFICULTIES, SPEEDS, TARGETS, Settings
from ..themes import THEMES, theme_manager
from .layout import vcenter_lines
from .render import get_term_size, invalidate_diff


@dataclass(frozen=True)
class _Row:
    key: str  # core field name, "theme", an action row, "extra:<toggle key>" or "back"
    label: str


_CORE_ROWS: tuple[_Row, ...] = (
    _Row("ai", "AI difficulty"),
    _Row("target", "Target score"),
    _Row("speed", "Speed"),
    _Row("theme", "Theme"),
    _Row("theme_files", "Theme files (import / export)"),
    _Row("card_back", "Card back"),
    _Row("table_frame", "Table frame"),
    _Row("animations", "Animations"),
    _Row("fast_redraw", "Fast redraw"),
    _Row("screen_reader", "Screen-reader hints"),
    _Row("mouse", "Mouse (click cards & shop)"),
    _Row("replay_analysis", "Post-round replay analysis"),
    _Row("controls", "Controls"),
)

# Rows that only open a screen (Enter); ←/→ do nothing on them.
_ACTION_ROWS: frozenset[str] = frozenset({"theme_files", "controls"})

_ENV_FOR: dict[str, str] = {
    "animations": "BELOTE_NO_ANIM",
    "fast_redraw": "BELOTE_NO_DIFF",
    "screen_reader": "BELOTE_A11Y",
    "mouse": "BELOTE_NO_MOUSE",
    "replay_analysis": "BELOTE_REPLAY",
}

_SEAT_KEYS: dict[Seat, str] = {Seat.EAST: "east", Seat.NORTH: "north", Seat.WEST: "west"}


def rows() -> list[_Row]:
    extra = [_Row(f"extra:{t.key}", t.label) for t in settings_mod.TOGGLES.values()]
    return [*_CORE_ROWS, *extra, _Row("back", "Back")]


def _on_off(v: bool) -> str:
    return "On" if v else "Off"


def _value(s: Settings, key: str) -> tuple[str, str | None]:
    """(display value, env var forcing a different effective value or None)."""
    if key == "ai":
        diffs = set(s.ai.values())
        return (next(iter(diffs)).capitalize() if len(diffs) == 1 else "Mixed"), None
    if key == "target":
        return str(s.target), None
    if key == "speed":
        return s.speed.capitalize(), None
    if key == "theme":
        return theme_manager.get_current().name, None
    if key == "card_back":
        return cosmetics.card_back(s.card_back).name, None
    if key == "table_frame":
        return cosmetics.table_frame(s.table_frame).name, None
    if key.startswith("extra:"):
        tkey = key[len("extra:") :]
        saved = s.extras.get(tkey, settings_mod.TOGGLES[tkey].default)
        forced = settings_mod.TOGGLES[tkey].env_var if s.extra_on(tkey) != saved else None
        return _on_off(saved), forced
    saved = bool(getattr(s, key))
    effective = bool(getattr(s, f"{key}_on")())
    return _on_off(saved), (_ENV_FOR[key] if effective != saved else None)


_LABEL_W = 30
_VALUE_CAP = 18  # imported theme names can be up to 32 characters


def _value_width() -> int:
    """One value-column width for every row (stable while cycling): the
    widest built-in option, capped; longer values are truncated with "…"."""
    names = [t.name for t in THEMES.values()]
    names += [b.name for b in cosmetics.CARD_BACKS.values()]
    names += [f.name for f in cosmetics.TABLE_FRAMES.values()]
    return min(_VALUE_CAP, max(10, *(visible_len(n) for n in names)))


def _fit(value: str, width: int) -> str:
    if visible_len(value) > width:
        value = ansi_truncate(value, width - 1) + "…"
    return ansi_center(value, width)


def _row_text(s: Settings, row: _Row, value_w: int) -> str:
    if row.key == "back":
        return "Back"
    if row.key in _ACTION_ROWS:
        return f"{row.label:<{_LABEL_W}}  {_fit('Enter ›', value_w)}  "
    value, forced = _value(s, row.key)
    text = f"{row.label:<{_LABEL_W}}< {_fit(value, value_w)} >"
    if forced:
        text += f"  {DIM}(forced by {forced}){RESET}"
    return text


def settings_lines(s: Settings, sel: int) -> list[str]:
    """Pure line-builder for the Settings screen. Every row is padded to the
    same visible width so the centred block keeps its columns aligned."""
    lines = [f"{BOLD}{gold_fg()}SETTINGS{RESET}", "", ""]
    all_rows = rows()
    value_w = _value_width()
    texts = [_row_text(s, row, value_w) for row in all_rows]
    width = max(visible_len(t) for t in texts)
    for i, (row, text) in enumerate(zip(all_rows, texts, strict=True)):
        if row.key == "back":
            lines.append("")
            text = ansi_center(text, width)
        else:
            text = ansi_ljust(text, width)
        lines.append(f"{REVERSE} {text} {RESET}" if i == sel else f" {text} ")
    lines += [
        "",
        f"{DIM}↑/↓ select   ←/→ change   Enter: details / toggle   Esc: back (saves){RESET}",
    ]
    if 0 <= sel < len(all_rows):
        lines += _preview(s, all_rows[sel].key)
    return lines


def _preview(s: Settings, key: str) -> list[str]:
    """Live preview under the list while a cosmetic row is selected."""
    from .customize import back_preview, frame_sample

    if key == "card_back":
        return ["", *back_preview(s.card_back, compact=True)]
    if key == "table_frame":
        return ["", *frame_sample(s.table_frame, compact=True)]
    return []


def _step(options: tuple[str, ...], current: str, delta: int) -> str:
    idx = options.index(current) if current in options else 0
    return options[(idx + delta) % len(options)]


def change(s: Settings, key: str, delta: int) -> None:
    """Step a row's value by ±1 (pure on `s` apart from the theme row)."""
    if key == "ai":
        diffs = set(s.ai.values())
        base = next(iter(diffs)) if len(diffs) == 1 else "medium"
        s.ai = dict.fromkeys(s.ai, _step(DIFFICULTIES, base, delta))
    elif key == "target":
        from .menu import _step_target  # nearest preset for a custom --target

        s.target = _step_target(list(TARGETS), s.target, delta)
    elif key == "speed":
        s.speed = _step(SPEEDS, s.speed, delta)
    elif key == "theme":
        theme_manager.cycle(delta)
    elif key == "card_back":  # only unlocked backs are reachable
        s.card_back = _step(tuple(cosmetics.unlocked_ids(CardBack)), s.card_back, delta)
    elif key == "table_frame":
        s.table_frame = _step(tuple(cosmetics.unlocked_ids(TableFrame)), s.table_frame, delta)
    elif key.startswith("extra:"):
        tkey = key[len("extra:") :]
        s.extras[tkey] = not s.extras.get(tkey, settings_mod.TOGGLES[tkey].default)
    elif key != "back" and key not in _ACTION_ROWS:
        setattr(s, key, not getattr(s, key))


def _open(reader: KeyReader, s: Settings, key: str) -> None:
    """Enter on a row: open its screen, or step it like →."""
    from . import customize
    from .menu import show_ai_config, show_theme_selector

    if key == "ai":
        seat_diffs = {seat: s.ai[name] for seat, name in _SEAT_KEYS.items()}
        chosen = show_ai_config(reader, seat_diffs)
        s.ai = {name: chosen[seat] for seat, name in _SEAT_KEYS.items()}
    elif key == "theme":
        show_theme_selector(reader)
    elif key == "card_back":
        customize.show_cosmetic_picker(reader, s, CardBack)
    elif key == "table_frame":
        customize.show_cosmetic_picker(reader, s, TableFrame)
    elif key == "theme_files":
        customize.show_theme_files(reader)
    elif key == "controls":
        customize.show_controls(reader, s)
    else:
        change(s, key, 1)


def show_settings(reader: KeyReader, s: Settings) -> None:
    """Interactive Settings screen. Mutates `s`, applies live, saves on exit."""
    sel = 0
    # Record milestones met elsewhere (e.g. a BelAtro run) so the pickers'
    # ←/→ cycling already offers them.
    cosmetics.check_unlocks()
    try:
        while True:
            all_rows = rows()
            term_w, term_h = get_term_size()
            lines = vcenter_lines(
                [ansi_center(line, term_w) for line in settings_lines(s, sel)], term_h
            )
            sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(lines))
            sys.stdout.flush()
            from . import hitmap

            hitmap.targets_from_lines(
                "menu", lines, [(r.label, i) for i, r in enumerate(all_rows)], full_row=True
            )

            event = reader.read()
            if event.key == Key.MOUSE:
                # 5.0.0: click a row to select it, click it again for Enter.
                clicked = hitmap.hit("menu", event.pos)
                if not isinstance(clicked, int):
                    continue
                if clicked != sel:
                    sel = clicked
                    continue
                event = KeyEvent(Key.ENTER)
            key = all_rows[sel].key
            match event.key:
                case Key.QUIT | Key.ESC | Key.EOF:
                    return
                case Key.UP:
                    sel = (sel - 1) % len(all_rows)
                case Key.DOWN:
                    sel = (sel + 1) % len(all_rows)
                case Key.LEFT | Key.RIGHT:
                    change(s, key, 1 if event.key == Key.RIGHT else -1)
                case Key.ENTER:
                    if key == "back":
                        return
                    _open(reader, s, key)
                case _:
                    continue
            settings_mod.apply(s)
    finally:
        settings_mod.apply(s)
        settings_mod.save(s)
        invalidate_diff()
