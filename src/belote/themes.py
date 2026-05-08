from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Theme:
    name: str
    felt_bg: tuple[int, int, int]
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
        card_face_bg=(245, 240, 220),
        face_card_bg=(245, 240, 220),
        card_back_bg=(50, 80, 150),
        highlight_bg=(255, 200, 0),  # orange highlight
        red_fg=(0, 100, 200),         # blue replaces red for ♥/♦
        black_fg=(20, 20, 20),
        white_fg=(245, 245, 240),
        gold_fg=(255, 200, 0),
        light_gray_fg=(160, 160, 160),
        green_fg=(0, 150, 200),       # cyan instead of green
        banner_bg=(50, 50, 80),
        banner_fg=(255, 200, 0),
        felt_placeholder_fg=(80, 80, 100),
        menu_art_fg=(255, 200, 0),
        menu_border_fg=(0, 150, 200),
    ),
}


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
            raise ValueError(
                f"Unknown theme {name!r}. Available: {sorted(THEMES.keys())}"
            )
        self._current_theme_name = name
        self.save_selection()
        # Execute registered callbacks (e.g., to clear UI caches)
        for callback in self._on_change_callbacks:
            callback()

    def list_themes(self) -> list[str]:
        return list(THEMES.keys())

    def load_selection(self) -> None:
        path = self._get_config_path()
        if path.exists():
            with contextlib.suppress(Exception), path.open() as f:
                data = json.load(f)
                name = data.get("theme", "classic_green")
                if name in THEMES:
                    self._current_theme_name = name

    def save_selection(self) -> None:
        path = self._get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception), path.open("w") as f:
            json.dump({"theme": self._current_theme_name}, f)

    def _get_config_path(self) -> Path:
        return Path.home() / ".config" / "belote" / "theme.json"


theme_manager = ThemeManager()
