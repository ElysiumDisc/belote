"""Persistent player settings (`settings.json` in the config directory).

Replaces the compile-time `BELOTE_*` environment flags as the normal way to
configure the game. The env vars still work and win over the saved setting
when set (handy for debugging), but players no longer need them.

`apply()` pushes the effective values into the modules that consume them;
call it after loading and after every change made in the Settings screen.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import config_dir

DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard")
SPEEDS: tuple[str, ...] = ("slow", "normal", "fast", "instant")
TARGETS: tuple[int, ...] = (500, 1000, 1500, 2000)
AI_SEATS: tuple[str, ...] = ("east", "north", "west")

_TRUTHY = {"1", "true", "yes", "on"}


def _default_ai() -> dict[str, str]:
    return dict.fromkeys(AI_SEATS, "medium")


@dataclass
class Settings:
    # Classic game setup (previously main-menu rows / CLI flags).
    ai: dict[str, str] = field(default_factory=_default_ai)
    target: int = 1000
    speed: str = "normal"
    # Display & accessibility (previously env vars).
    animations: bool = True  # BELOTE_NO_ANIM=1 forces off
    fast_redraw: bool = True  # BELOTE_NO_DIFF=1 forces off (diff renderer)
    screen_reader: bool = False  # BELOTE_A11Y=1 forces on
    # Extras (previously env vars).
    replay_analysis: bool = False  # BELOTE_REPLAY forces on
    # On/off settings contributed by expansions (see `register_toggle`).
    extras: dict[str, bool] = field(default_factory=dict)
    # 4.11.0 cosmetics (ids in `cosmetics.CARD_BACKS` / `TABLE_FRAMES`).
    card_back: str = "classique"
    table_frame: str = "art_nouveau"
    # 4.11.0 rebound keys: action → key, only the actions the player changed
    # (see `input.BINDINGS`); validated as a whole on load.
    keys: dict[str, str] = field(default_factory=dict)

    # ── effective values (env override applied) ────────────────────────

    def animations_on(self) -> bool:
        return self.animations and os.environ.get("BELOTE_NO_ANIM") != "1"

    def fast_redraw_on(self) -> bool:
        return self.fast_redraw and os.environ.get("BELOTE_NO_DIFF") != "1"

    def screen_reader_on(self) -> bool:
        return self.screen_reader or os.environ.get("BELOTE_A11Y", "").lower() in _TRUTHY

    def replay_analysis_on(self) -> bool:
        return self.replay_analysis or bool(os.environ.get("BELOTE_REPLAY"))

    def extra_on(self, key: str) -> bool:
        """Effective value of a registered toggle (its env var forces it on)."""
        toggle = TOGGLES.get(key)
        default = toggle.default if toggle else False
        forced = bool(toggle and toggle.env_var and os.environ.get(toggle.env_var))
        return self.extras.get(key, default) or forced


@dataclass(frozen=True)
class Toggle:
    """An on/off setting an expansion adds to the Settings screen."""

    key: str
    label: str
    default: bool = False
    env_var: str | None = None  # setting this env var forces the toggle on


TOGGLES: dict[str, Toggle] = {}


def register_toggle(toggle: Toggle) -> None:
    TOGGLES[toggle.key] = toggle


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load() -> Settings:
    """Saved settings, falling back to defaults for anything missing, unknown
    or invalid (a corrupt file never blocks the game from starting)."""
    s = Settings()
    try:
        raw = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        return s
    if not isinstance(raw, dict):
        return s
    ai = raw.get("ai")
    if isinstance(ai, dict):
        for seat in AI_SEATS:
            if ai.get(seat) in DIFFICULTIES:
                s.ai[seat] = ai[seat]
    if raw.get("target") in TARGETS or (isinstance(raw.get("target"), int) and raw["target"] > 0):
        s.target = int(raw["target"])
    if raw.get("speed") in SPEEDS:
        s.speed = raw["speed"]
    for f in fields(Settings):
        if f.type == "bool" and isinstance(raw.get(f.name), bool):
            setattr(s, f.name, raw[f.name])
    extras = raw.get("extras")
    if isinstance(extras, dict):
        s.extras = {k: v for k, v in extras.items() if isinstance(k, str) and isinstance(v, bool)}
    _load_customisation(raw, s)
    return s


def _load_customisation(raw: dict[str, object], s: Settings) -> None:
    """4.11.0 keys; files written before them simply keep the defaults. An
    unknown back/frame id, or a key map with any conflict, is ignored."""
    from .cosmetics import CARD_BACKS, TABLE_FRAMES
    from .input import DEFAULT_BINDINGS, validate_bindings

    back, frame, keys = raw.get("card_back"), raw.get("table_frame"), raw.get("keys")
    if isinstance(back, str) and back in CARD_BACKS:
        s.card_back = back
    if isinstance(frame, str) and frame in TABLE_FRAMES:
        s.table_frame = frame
    if isinstance(keys, dict):
        cand = {
            a: k.lower()
            for a, k in keys.items()
            if isinstance(a, str) and a in DEFAULT_BINDINGS and isinstance(k, str)
        }
        if validate_bindings(cand) is None:
            s.keys = cand


def save(s: Settings) -> None:
    """Atomic write (temp file + replace); failures are swallowed — settings
    are a convenience, never a reason to crash."""
    path = settings_path()
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=".settings-", suffix=".tmp", delete=False
        ) as tf:
            tmp = Path(tf.name)
            json.dump(asdict(s), tf, indent=2, sort_keys=True)
        tmp.replace(path)
    except OSError:
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink()


_current = Settings()


def current() -> Settings:
    """The settings most recently applied (defaults until `apply` runs)."""
    return _current


def apply(s: Settings) -> None:
    """Make `s` the active settings and push effective values into the
    modules that cache them."""
    global _current
    _current = s
    from . import a11y, cosmetics
    from . import input as input_mod
    from .ui.anim import set_animations_enabled
    from .ui.render import set_diff_enabled

    set_animations_enabled(s.animations_on())
    set_diff_enabled(s.fast_redraw_on())
    a11y.set_enabled(s.screen_reader_on())
    cosmetics.set_active(back=s.card_back, frame=s.table_frame)
    try:
        input_mod.set_bindings(s.keys)
    except ValueError:
        input_mod.set_bindings({})
