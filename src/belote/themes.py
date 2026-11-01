from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

from .paths import config_dir


@dataclass(frozen=True)
class Theme:
    name: str
    felt_bg: tuple[int, int, int]
    felt_edge_bg: tuple[int, int, int]
    card_face_bg: tuple[int, int, int]
    face_card_bg: tuple[int, int, int]
    card_back_bg: tuple[int, int, int]
    highlight_bg: tuple[int, int, int]
    red_fg: tuple[int, int, int]
    black_fg: tuple[int, int, int]
    white_fg: tuple[int, int, int]
    gold_fg: tuple[int, int, int]
    light_gray_fg: tuple[int, int, int]
    green_fg: tuple[int, int, int]
    banner_bg: tuple[int, int, int]
    banner_fg: tuple[int, int, int]
    felt_placeholder_fg: tuple[int, int, int]
    menu_art_fg: tuple[int, int, int]
    menu_border_fg: tuple[int, int, int]


THEMES: dict[str, Theme] = {
    "classic_green": Theme(
        name="Classic Green",
        felt_bg=(25, 75, 45),
        felt_edge_bg=(15, 50, 30),
        card_face_bg=(248, 245, 230),
        face_card_bg=(250, 240, 200),
        card_back_bg=(110, 35, 35),
        highlight_bg=(230, 190, 70),
        red_fg=(190, 45, 45),
        black_fg=(40, 40, 40),
        white_fg=(235, 235, 230),
        gold_fg=(210, 170, 60),
        light_gray_fg=(160, 160, 155),
        green_fg=(60, 160, 90),
        banner_bg=(50, 65, 120),
        banner_fg=(240, 220, 150),
        felt_placeholder_fg=(40, 100, 60),
        menu_art_fg=(210, 170, 60),
        menu_border_fg=(60, 160, 90),
    ),
    "dark_mode": Theme(
        name="Dark Mode",
        felt_bg=(26, 26, 46),
        felt_edge_bg=(16, 16, 30),
        card_face_bg=(45, 45, 60),
        face_card_bg=(60, 60, 80),
        card_back_bg=(80, 40, 120),
        highlight_bg=(0, 255, 255),
        red_fg=(255, 80, 80),
        black_fg=(200, 200, 220),
        white_fg=(240, 240, 255),
        gold_fg=(0, 255, 150),
        light_gray_fg=(120, 120, 140),
        green_fg=(0, 200, 200),
        banner_bg=(30, 30, 60),
        banner_fg=(0, 255, 255),
        felt_placeholder_fg=(40, 40, 70),
        menu_art_fg=(0, 255, 255),
        menu_border_fg=(100, 100, 255),
    ),
    "blue_velvet": Theme(
        name="Blue Velvet",
        felt_bg=(26, 39, 68),
        felt_edge_bg=(15, 24, 44),
        card_face_bg=(240, 240, 245),
        face_card_bg=(220, 230, 240),
        card_back_bg=(40, 60, 100),
        highlight_bg=(180, 180, 200),
        red_fg=(200, 60, 60),
        black_fg=(30, 30, 50),
        white_fg=(255, 255, 255),
        gold_fg=(200, 200, 220),
        light_gray_fg=(150, 150, 170),
        green_fg=(80, 150, 180),
        banner_bg=(20, 30, 50),
        banner_fg=(200, 220, 255),
        felt_placeholder_fg=(40, 60, 100),
        menu_art_fg=(180, 180, 200),
        menu_border_fg=(100, 150, 200),
    ),
    "red_casino": Theme(
        name="Red Casino",
        felt_bg=(74, 21, 32),
        felt_edge_bg=(46, 12, 20),
        card_face_bg=(250, 245, 235),
        face_card_bg=(255, 235, 200),
        card_back_bg=(40, 40, 40),
        highlight_bg=(218, 165, 32),
        red_fg=(220, 20, 60),
        black_fg=(20, 20, 20),
        white_fg=(255, 250, 240),
        gold_fg=(255, 215, 0),
        light_gray_fg=(180, 160, 160),
        green_fg=(34, 139, 34),
        banner_bg=(139, 0, 0),
        banner_fg=(255, 215, 0),
        felt_placeholder_fg=(100, 40, 50),
        menu_art_fg=(255, 215, 0),
        menu_border_fg=(178, 34, 34),
    ),
    "sepia_vintage": Theme(
        name="Sepia Vintage",
        felt_bg=(61, 46, 31),
        felt_edge_bg=(38, 29, 20),
        card_face_bg=(225, 205, 175),
        face_card_bg=(210, 180, 140),
        card_back_bg=(80, 50, 30),
        highlight_bg=(205, 133, 63),
        red_fg=(165, 42, 42),
        black_fg=(60, 40, 30),
        white_fg=(245, 245, 220),
        gold_fg=(184, 134, 11),
        light_gray_fg=(140, 130, 120),
        green_fg=(107, 142, 35),
        banner_bg=(92, 64, 51),
        banner_fg=(222, 184, 135),
        felt_placeholder_fg=(90, 70, 50),
        menu_art_fg=(184, 134, 11),
        menu_border_fg=(139, 69, 19),
    ),
    "high_contrast": Theme(
        name="High Contrast",
        felt_bg=(0, 0, 0),
        felt_edge_bg=(0, 0, 0),
        card_face_bg=(255, 255, 255),
        face_card_bg=(255, 255, 255),
        card_back_bg=(0, 0, 255),
        highlight_bg=(255, 255, 0),
        red_fg=(255, 0, 0),
        black_fg=(0, 0, 0),
        white_fg=(255, 255, 255),
        gold_fg=(255, 255, 0),
        light_gray_fg=(200, 200, 200),
        green_fg=(0, 255, 0),
        banner_bg=(0, 0, 255),
        banner_fg=(255, 255, 255),
        felt_placeholder_fg=(100, 100, 100),
        menu_art_fg=(255, 255, 255),
        menu_border_fg=(255, 255, 255),
    ),
    # 3.0.0: colorblind-friendly palette (deuteranopia/protanopia-safe).
    # Uses blue/orange/yellow/cyan instead of red/green for the suit-card
    # contrast. Pair with shape glyphs in render.py if more disambiguation
    # is needed downstream.
    "colorblind": Theme(
        name="Colorblind",
        felt_bg=(40, 40, 50),
        felt_edge_bg=(25, 25, 34),
        card_face_bg=(245, 240, 220),
        face_card_bg=(245, 240, 220),
        card_back_bg=(50, 80, 150),
        highlight_bg=(255, 200, 0),  # orange highlight
        red_fg=(0, 100, 200),  # blue replaces red for ♥/♦
        black_fg=(20, 20, 20),
        white_fg=(245, 245, 240),
        gold_fg=(255, 200, 0),
        light_gray_fg=(160, 160, 160),
        green_fg=(0, 150, 200),  # cyan instead of green
        banner_bg=(50, 50, 80),
        banner_fg=(255, 200, 0),
        felt_placeholder_fg=(80, 80, 100),
        menu_art_fg=(255, 200, 0),
        menu_border_fg=(0, 150, 200),
    ),
    # 3.9.4: four new themes plus felt_edge_bg field for vignette gradient.
    "forest_night": Theme(
        name="Forest Night",
        felt_bg=(18, 42, 28),
        felt_edge_bg=(10, 26, 18),
        card_face_bg=(238, 230, 210),
        face_card_bg=(245, 232, 200),
        card_back_bg=(60, 38, 22),
        highlight_bg=(212, 158, 60),  # lantern gold
        red_fg=(180, 60, 50),
        black_fg=(35, 30, 25),
        white_fg=(228, 222, 200),
        gold_fg=(212, 158, 60),  # copper / lantern
        light_gray_fg=(145, 138, 120),
        green_fg=(90, 150, 95),
        banner_bg=(28, 50, 32),
        banner_fg=(232, 200, 130),
        felt_placeholder_fg=(60, 95, 70),
        menu_art_fg=(212, 158, 60),
        menu_border_fg=(90, 130, 80),
    ),
    "moonlit_tavern": Theme(
        name="Moonlit Tavern",
        felt_bg=(32, 38, 56),
        felt_edge_bg=(20, 24, 38),
        card_face_bg=(240, 226, 196),  # parchment
        face_card_bg=(245, 232, 200),
        card_back_bg=(70, 50, 30),
        highlight_bg=(220, 170, 80),  # candle amber
        red_fg=(180, 55, 60),
        black_fg=(40, 35, 30),
        white_fg=(230, 224, 210),
        gold_fg=(220, 170, 80),
        light_gray_fg=(140, 140, 160),
        green_fg=(110, 150, 145),
        banner_bg=(40, 50, 70),
        banner_fg=(232, 200, 140),
        felt_placeholder_fg=(70, 80, 105),
        menu_art_fg=(220, 170, 80),
        menu_border_fg=(140, 150, 180),
    ),
    "royal_purple": Theme(
        name="Royal Purple",
        felt_bg=(48, 24, 64),
        felt_edge_bg=(32, 14, 44),
        card_face_bg=(245, 238, 230),  # ivory
        face_card_bg=(250, 232, 200),
        card_back_bg=(35, 18, 50),
        highlight_bg=(212, 175, 55),  # gold
        red_fg=(190, 50, 70),
        black_fg=(35, 25, 40),
        white_fg=(238, 232, 240),
        gold_fg=(212, 175, 55),
        light_gray_fg=(170, 158, 175),
        green_fg=(120, 140, 175),
        banner_bg=(60, 30, 80),
        banner_fg=(225, 200, 240),
        felt_placeholder_fg=(85, 55, 100),
        menu_art_fg=(212, 175, 55),
        menu_border_fg=(180, 160, 200),
    ),
    "emerald_isle": Theme(
        name="Emerald Isle",
        felt_bg=(12, 70, 50),
        felt_edge_bg=(6, 46, 32),
        card_face_bg=(245, 240, 220),  # cream
        face_card_bg=(248, 238, 200),
        card_back_bg=(70, 50, 22),  # brass
        highlight_bg=(212, 175, 55),  # brass gold
        red_fg=(178, 48, 56),
        black_fg=(30, 35, 30),
        white_fg=(232, 230, 215),
        gold_fg=(212, 175, 55),
        light_gray_fg=(150, 160, 150),
        green_fg=(80, 175, 130),
        banner_bg=(20, 60, 45),
        banner_fg=(232, 210, 150),
        felt_placeholder_fg=(50, 100, 80),
        menu_art_fg=(212, 175, 55),
        menu_border_fg=(110, 170, 130),
    ),
    # 4.8.0: warm sunset/magma palette — fills the orange/magenta niche left
    # open by the cool/dark/earthy spread of the first 11 themes. Deep magenta
    # felt, coral suits, smoky-purple "blacks", amber-sunset highlights.
    "sunset_magma": Theme(
        name="Sunset Magma",
        felt_bg=(92, 28, 60),  # deep magenta
        felt_edge_bg=(58, 16, 38),  # rose edge
        card_face_bg=(248, 232, 210),  # warm cream
        face_card_bg=(252, 226, 188),  # peach-cream
        card_back_bg=(168, 50, 70),  # rose
        highlight_bg=(248, 168, 92),  # amber
        red_fg=(228, 88, 78),  # coral
        black_fg=(72, 38, 70),  # smoky purple
        white_fg=(248, 238, 226),
        gold_fg=(232, 168, 78),  # amber-sunset
        light_gray_fg=(178, 150, 160),
        green_fg=(140, 138, 96),  # olive accent
        banner_bg=(126, 36, 78),  # magenta
        banner_fg=(248, 232, 210),  # cream
        felt_placeholder_fg=(132, 60, 92),
        menu_art_fg=(232, 168, 78),
        menu_border_fg=(228, 88, 78),
    ),
    # 4.9.1: sun-soaked Provençal lavender field — vivid lavender felt,
    # sun-parchment cards, aubergine card backs, mauve-wine suits, honey-gold
    # highlights, deep indigo banners. 4.9.1 second pass: pushed felt and
    # accents purplier per user feedback; the original terracotta accents
    # were overwhelming the lavender and reading as red. Real lavender
    # fields are unambiguously purple — the palette now coordinates around
    # that with warm honey-gold (NOT terracotta) as the only warm accent
    # for selection visibility.
    "provence_lavande": Theme(
        name="Provence Lavande",
        felt_bg=(160, 130, 210),  # vivid lavender field
        felt_edge_bg=(95, 70, 135),  # deep mauve vignette
        card_face_bg=(248, 240, 220),  # sun-parchment
        face_card_bg=(252, 235, 195),  # warmer parchment for face cards
        card_back_bg=(95, 65, 130),  # aubergine plum back
        highlight_bg=(225, 185, 105),  # honey-gold (warm + visible on lavender)
        red_fg=(170, 50, 95),  # mauve-wine ♥/♦
        black_fg=(45, 35, 65),  # deep aubergine-noir ♠/♣
        white_fg=(248, 240, 220),  # parchment
        gold_fg=(225, 185, 105),  # honey-gold
        light_gray_fg=(185, 170, 205),  # lilac-gray
        green_fg=(130, 150, 100),  # herb green
        banner_bg=(55, 40, 115),  # deep indigo-violet
        banner_fg=(248, 240, 220),  # parchment
        felt_placeholder_fg=(110, 85, 150),
        menu_art_fg=(225, 185, 105),  # honey-gold
        menu_border_fg=(175, 130, 200),  # soft orchid
    ),
}


# ── theme files (4.11.0 import / export) ──────────────────────────────────
#
# Format of `<config dir>/themes/<stem>.json`:
#   {"format": "belote-theme", "version": 1, "name": "My Theme",
#    "colors": {"felt_bg": "#194b2d", ..., "menu_border_fg": [60, 160, 90]}}
# Every colour field of `Theme` is required, no others are allowed; a colour
# is "#rrggbb" or a 3-int [r, g, b] list (0-255). Imported files are
# untrusted: size-capped, strictly validated, and registered under
# "custom:<stem>" so they can never replace a built-in theme.

THEME_FORMAT = "belote-theme"
THEME_FORMAT_VERSION = 1
MAX_THEME_BYTES = 8 * 1024
MAX_THEME_NAME = 32
CUSTOM_PREFIX = "custom:"
COLOR_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Theme) if f.name != "name")
_TOP_KEYS = frozenset({"format", "version", "name", "colors"})
_STEM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


class ThemeFileError(ValueError):
    """A theme file was rejected. The message is safe to show the player (it
    never echoes raw file content)."""


def theme_files_dir() -> Path:
    return config_dir() / "themes"


def _safe_stem(text: str) -> str:
    """A filesystem-safe file stem (no separators, dots or traversal)."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_-")[:40]
    return stem or "theme"


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def theme_to_dict(theme: Theme) -> dict[str, object]:
    return {
        "format": THEME_FORMAT,
        "version": THEME_FORMAT_VERSION,
        "name": theme.name,
        "colors": {k: _hex(getattr(theme, k)) for k in COLOR_FIELDS},
    }


def export_theme(key: str) -> Path:
    """Write theme `key` to `<config dir>/themes/<stem>.json` (atomic,
    overwriting an earlier export of the same theme). Raises OSError."""
    theme = THEMES[key]
    folder = theme_files_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_stem(key.removeprefix(CUSTOM_PREFIX))}.json"
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=folder, prefix=".theme-", suffix=".tmp", delete=False, encoding="utf-8"
        ) as tf:
            tmp = Path(tf.name)
            json.dump(theme_to_dict(theme), tf, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except OSError:
        if tmp is not None:
            with contextlib.suppress(OSError):
                tmp.unlink()
        raise
    return path


def list_theme_files() -> list[Path]:
    """Importable files in the themes folder: regular (non-symlink) `.json`
    files with a safe name, sorted. A missing folder lists nothing."""
    try:
        entries = sorted(theme_files_dir().iterdir())
    except OSError:
        return []
    return [
        p
        for p in entries
        if p.suffix == ".json" and _STEM_RE.fullmatch(p.stem) and not p.is_symlink() and p.is_file()
    ]


def _parse_color(key: str, value: object) -> tuple[int, int, int]:
    if isinstance(value, str) and _HEX_RE.fullmatch(value):
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    if (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    ):
        return (value[0], value[1], value[2])
    raise ThemeFileError(f'"{key}" must be "#rrggbb" or [r, g, b] with values 0-255')


def _parse_name(value: object) -> str:
    if not isinstance(value, str):
        raise ThemeFileError('"name" must be a string')
    name = value.strip()
    if not name or len(name) > MAX_THEME_NAME or not name.isprintable():
        raise ThemeFileError(f'"name" must be 1-{MAX_THEME_NAME} printable characters')
    return name


def _check_header(data: dict[object, object]) -> None:
    unknown = [k for k in data if k not in _TOP_KEYS]
    if unknown:
        raise ThemeFileError(f"unknown field(s): {len(unknown)} not allowed")
    if data.get("format", THEME_FORMAT) != THEME_FORMAT:
        raise ThemeFileError(f'"format" must be "{THEME_FORMAT}"')
    if data.get("version", THEME_FORMAT_VERSION) != THEME_FORMAT_VERSION:
        raise ThemeFileError(f"unsupported version (expected {THEME_FORMAT_VERSION})")


def parse_theme(raw: bytes) -> Theme:
    """Strictly validate theme-file bytes. Raises ThemeFileError."""
    if len(raw) > MAX_THEME_BYTES:
        raise ThemeFileError(f"file is larger than {MAX_THEME_BYTES // 1024} KiB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ThemeFileError("not valid UTF-8 JSON") from None
    if not isinstance(data, dict):
        raise ThemeFileError("top level must be a JSON object")
    _check_header(data)
    colors = data.get("colors")
    if not isinstance(colors, dict):
        raise ThemeFileError('"colors" must be an object')
    unknown = [k for k in colors if k not in COLOR_FIELDS]
    if unknown:
        raise ThemeFileError(f"{len(unknown)} unknown colour key(s)")
    missing = [k for k in COLOR_FIELDS if k not in colors]
    if missing:
        raise ThemeFileError(f'missing colour "{missing[0]}" ({len(missing)} missing)')
    parsed = {k: _parse_color(k, colors[k]) for k in COLOR_FIELDS}
    return Theme(name=_parse_name(data.get("name")), **parsed)


def _read_capped(path: Path) -> bytes:
    folder = theme_files_dir()
    if not _STEM_RE.fullmatch(path.stem) or path.suffix != ".json":
        raise ThemeFileError("file name must be letters, digits, '-' or '_' + .json")
    try:
        if path.is_symlink() or path.resolve().parent != folder.resolve():
            raise ThemeFileError("file must be inside the themes folder")
        if path.stat().st_size > MAX_THEME_BYTES:
            raise ThemeFileError(f"file is larger than {MAX_THEME_BYTES // 1024} KiB")
        with path.open("rb") as f:
            return f.read(MAX_THEME_BYTES + 1)
    except OSError:
        raise ThemeFileError("file could not be read") from None


def import_theme(path: Path) -> str:
    """Validate and register a theme file; returns its THEMES key
    (``custom:<stem>``). Does not activate it. Raises ThemeFileError."""
    theme = parse_theme(_read_capped(path))
    key = CUSTOM_PREFIX + path.stem
    THEMES[key] = theme
    return key


class ThemeManager:
    """Process-wide theme state. The module-level `theme_manager` instance is
    the singleton; constructing `ThemeManager()` again returns the same object.
    """

    _instance: ThemeManager | None = None

    def __new__(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Re-construction returns the singleton (see __new__) but __init__
        # still runs on every call. Guard the actual setup.
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._current_theme_name: str = "classic_green"
        self._on_change_callbacks: list[Callable[[], None]] = []
        self.load_selection()

    @property
    def current_name(self) -> str:
        """Public read-only accessor for the active theme's key in THEMES."""
        return self._current_theme_name

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be executed when the theme changes."""
        self._on_change_callbacks.append(callback)

    def get_current(self) -> Theme:
        return THEMES.get(self._current_theme_name, THEMES["classic_green"])

    def set_current(self, name: str) -> None:
        if name not in THEMES:
            raise ValueError(f"Unknown theme {name!r}. Available: {sorted(THEMES.keys())}")
        self._current_theme_name = name
        # Execute registered callbacks (e.g., to clear UI caches) before
        # persisting, so a failed save can never leave caches stale.
        for callback in self._on_change_callbacks:
            callback()
        self.save_selection()

    def cycle(self, step: int = 1) -> str:
        """Switch to the theme `step` places after the current one (wrapping)
        and return its name. An unknown current name restarts at the first."""
        names = list(THEMES.keys())
        try:
            idx = names.index(self._current_theme_name)
        except ValueError:
            idx = -step
        name = names[(idx + step) % len(names)]
        self.set_current(name)
        return name

    def list_themes(self) -> list[str]:
        return list(THEMES.keys())

    def load_selection(self) -> None:
        path = self._get_config_path()
        if path.exists():
            with contextlib.suppress(Exception), path.open() as f:
                data = json.load(f)
                name = data.get("theme", "classic_green")
                if isinstance(name, str) and name.startswith(CUSTOM_PREFIX) and name not in THEMES:
                    # An imported theme: re-read its file (falls back to the
                    # default when it was removed or no longer validates).
                    import_theme(theme_files_dir() / f"{name.removeprefix(CUSTOM_PREFIX)}.json")
                if name in THEMES:
                    self._current_theme_name = name

    def save_selection(self) -> None:
        """Persist the theme choice. Best-effort: a read-only or missing
        config dir must not crash the app when the player presses T, so every
        filesystem step (including mkdir) is inside the OSError guard. Written
        to a sibling tmp file then os.replace'd so a crash can't truncate it."""
        path = self._get_config_path()
        tmp_path: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(path.parent),
                prefix=".theme-",
                suffix=".json.tmp",
                delete=False,
            ) as tf:
                tmp_path = Path(tf.name)
                json.dump({"theme": self._current_theme_name}, tf)
                tf.flush()
                os.fsync(tf.fileno())
            tmp_path.replace(path)
        except OSError:
            if tmp_path is not None:
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    def _get_config_path(self) -> Path:
        # Honors XDG_CONFIG_HOME / %APPDATA% (pre-4.10.0 hardcoded ~/.config,
        # which also let the test suite write the real user config).
        return config_dir() / "theme.json"


theme_manager = ThemeManager()
