"""Settings screen: game setup, display/accessibility and extras.

Every change applies immediately (`settings.apply`) and is saved when the
screen closes. Rows contributed by expansions (`settings.register_toggle`)
appear after the core rows.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .. import settings as settings_mod
from ..ansi import BOLD, DIM, RESET, REVERSE, ansi_center, clear_screen, gold_fg, hide_cursor
from ..game import Seat
from ..input import Key, KeyReader
from ..settings import DIFFICULTIES, SPEEDS, TARGETS, Settings
from ..themes import theme_manager
from .layout import vcenter_lines
from .render import get_term_size, invalidate_diff


@dataclass(frozen=True)
class _Row:
    key: str  # core field name, "theme", "extra:<toggle key>" or "back"
    label: str


_CORE_ROWS: tuple[_Row, ...] = (
    _Row("ai", "AI difficulty"),
    _Row("target", "Target score"),
    _Row("speed", "Speed"),
    _Row("theme", "Theme"),
    _Row("animations", "Animations"),
    _Row("fast_redraw", "Fast redraw"),
    _Row("screen_reader", "Screen-reader hints"),
    _Row("replay_analysis", "Post-round replay analysis"),
)

_ENV_FOR: dict[str, str] = {
    "animations": "BELOTE_NO_ANIM",
    "fast_redraw": "BELOTE_NO_DIFF",
    "screen_reader": "BELOTE_A11Y",
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
    if key.startswith("extra:"):
        tkey = key[len("extra:"):]
        saved = s.extras.get(tkey, settings_mod.TOGGLES[tkey].default)
        forced = settings_mod.TOGGLES[tkey].env_var if s.extra_on(tkey) != saved else None
        return _on_off(saved), forced
    saved = bool(getattr(s, key))
    effective = bool(getattr(s, f"{key}_on")())
    return _on_off(saved), (_ENV_FOR[key] if effective != saved else None)


def settings_lines(s: Settings, sel: int) -> list[str]:
    """Pure line-builder for the Settings screen."""
    lines = [f"{BOLD}{gold_fg()}SETTINGS{RESET}", "", ""]
    for i, row in enumerate(rows()):
        if row.key == "back":
            lines.append("")
            text = "Back"
        else:
            value, forced = _value(s, row.key)
            text = f"{row.label:<28} < {value:^10} >"
            if forced:
                text += f"  {DIM}(forced by {forced}){RESET}"
        lines.append(f"{REVERSE} {text} {RESET}" if i == sel else f" {text} ")
    lines += [
        "",
        f"{DIM}↑/↓ select   ←/→ change   Enter: details / toggle   Esc: back (saves){RESET}",
    ]
    return lines


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
    elif key.startswith("extra:"):
        tkey = key[len("extra:"):]
        s.extras[tkey] = not s.extras.get(tkey, settings_mod.TOGGLES[tkey].default)
    elif key != "back":
        setattr(s, key, not getattr(s, key))


def show_settings(reader: KeyReader, s: Settings) -> None:
    """Interactive Settings screen. Mutates `s`, applies live, saves on exit."""
    from .menu import show_ai_config, show_theme_selector

    sel = 0
    try:
        while True:
            all_rows = rows()
            term_w, term_h = get_term_size()
            lines = [ansi_center(line, term_w) for line in settings_lines(s, sel)]
            sys.stdout.write(clear_screen() + hide_cursor() + "\r\n".join(vcenter_lines(lines, term_h)))
            sys.stdout.flush()

            event = reader.read()
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
                    if key == "ai":
                        seat_diffs = {seat: s.ai[name] for seat, name in _SEAT_KEYS.items()}
                        chosen = show_ai_config(reader, seat_diffs)
                        s.ai = {name: chosen[seat] for seat, name in _SEAT_KEYS.items()}
                    elif key == "theme":
                        show_theme_selector(reader)
                    else:
                        change(s, key, 1)
                case _:
                    continue
            settings_mod.apply(s)
    finally:
        settings_mod.apply(s)
        settings_mod.save(s)
        invalidate_diff()
