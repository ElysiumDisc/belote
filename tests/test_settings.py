"""Persistent settings (`belote.settings`) and the Settings screen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from belote import settings as settings_mod
from belote.settings import Settings, Toggle


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for var in ("BELOTE_NO_ANIM", "BELOTE_NO_DIFF", "BELOTE_A11Y", "BELOTE_REPLAY", "BELOTE_GHOST"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "belote" / "settings.json"


def test_roundtrip(cfg: Path) -> None:
    s = Settings(target=1500, speed="fast", animations=False, extras={"x": True})
    s.ai["north"] = "hard"
    settings_mod.save(s)
    loaded = settings_mod.load()
    assert loaded == s
    assert json.loads(cfg.read_text())["speed"] == "fast"


def test_missing_corrupt_and_invalid_values_fall_back(cfg: Path) -> None:
    assert settings_mod.load() == Settings()
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{not json")
    assert settings_mod.load() == Settings()
    cfg.write_text(json.dumps({"speed": "ludicrous", "ai": {"east": "god"}, "animations": "yes"}))
    assert settings_mod.load() == Settings()


def test_env_vars_override_saved_values(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    assert s.animations_on() and s.fast_redraw_on() and not s.screen_reader_on()
    monkeypatch.setenv("BELOTE_NO_ANIM", "1")
    monkeypatch.setenv("BELOTE_NO_DIFF", "1")
    monkeypatch.setenv("BELOTE_A11Y", "1")
    monkeypatch.setenv("BELOTE_REPLAY", "1")
    assert not s.animations_on() and not s.fast_redraw_on()
    assert s.screen_reader_on() and s.replay_analysis_on()


def test_registered_toggle(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(settings_mod.TOGGLES, "t1", Toggle("t1", "Test toggle", False, "T1_ENV"))
    s = Settings()
    assert not s.extra_on("t1")
    s.extras["t1"] = True
    assert s.extra_on("t1")
    s.extras["t1"] = False
    monkeypatch.setenv("T1_ENV", "1")
    assert s.extra_on("t1")


def test_apply_pushes_into_modules(cfg: Path) -> None:
    from belote import a11y
    from belote.ui import anim

    render = __import__("belote.ui.render", fromlist=["_DIFF_ENABLED"])
    try:
        settings_mod.apply(Settings(animations=False, fast_redraw=False, screen_reader=True))
        assert not anim.animations_enabled()
        assert render._DIFF_ENABLED is False
        assert a11y.is_enabled()
        assert settings_mod.current().screen_reader
    finally:
        settings_mod.apply(Settings())
    assert anim.animations_enabled() and render._DIFF_ENABLED and not a11y.is_enabled()


def test_settings_screen_lines_and_changes(cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.ui import settings_menu

    s = Settings()
    keys = [r.key for r in settings_menu.rows()]
    assert keys[0] == "ai" and keys[-1] == "back"
    settings_menu.change(s, "ai", 1)
    assert set(s.ai.values()) == {"hard"}
    settings_menu.change(s, "speed", -1)
    assert s.speed == "slow"
    settings_menu.change(s, "animations", 1)
    assert s.animations is False
    monkeypatch.setenv("BELOTE_NO_DIFF", "1")
    joined = "\n".join(settings_menu.settings_lines(s, 0))
    assert "Fast redraw" in joined and "(forced by BELOTE_NO_DIFF)" in joined
    assert "Hard" in joined


def test_main_menu_lists_injected_modes_first() -> None:
    import io
    import sys

    from belote.input import Key, KeyEvent
    from belote.ui import menu

    class _R:
        def __init__(self) -> None:
            self.events = [KeyEvent(Key.ENTER)]

        def read_timeout(self, _t: float) -> KeyEvent:
            return self.events.pop(0)

    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        assert menu.show_main_menu(_R(), ["Mode A", "Mode B"]) == "Mode A"  # type: ignore[arg-type]
        out = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    assert "Settings" in out and "Mode B" in out
