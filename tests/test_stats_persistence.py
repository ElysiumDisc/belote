"""Persistence robustness: stats.json, theme.json and the stats path.

- `save_stats` used to open stats.json with "w" (truncate first), so a crash
  mid-write lost the whole history. Now tmp file + fsync + os.replace.
- `load_stats` crashed (or later crashed in `update_stats_round`) on non-dict
  JSON, non-UTF-8 bytes and wrong-typed fields, and silently overwrote an
  unparseable file on the next save. Now: per-field defaults, and corrupt
  files are moved aside to `stats.json.bak`.
- `ThemeManager.save_selection` did `mkdir` outside its error guard, so a
  read-only config dir crashed the app when the player pressed T.
- `Config.stats_path` ignored %APPDATA% on Windows (BelAtro's save honours it).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from belote.stats import Statistics, StatisticsManager

# ── load_stats ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [b"[]", b"null", b"42", b"\xff\xfe{", b'{"games_played": 42, "games_w'],
    ids=["list", "null", "number", "non-utf8", "truncated"],
)
def test_unparseable_stats_fall_back_and_are_moved_aside(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "stats.json"
    path.write_bytes(content)
    mgr = StatisticsManager(path)

    stats = mgr.load_stats()
    assert stats == Statistics()
    backup = tmp_path / "stats.json.bak"
    assert backup.read_bytes() == content
    # And a round update works on the defaults (used to crash for some).
    mgr.update_stats_round(False, 80, "♠")
    assert json.loads(path.read_text())["total_rounds"] == 1
    assert backup.read_bytes() == content


def test_wrong_typed_fields_fall_back_per_field(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    path.write_text(
        json.dumps(
            {
                "games_played": 7,
                "games_won": "lots",
                "capots_achieved": True,
                "most_used_trump": None,
                "difficulty_stats": {"hard": {"played": 3, "won": None}, "nope": 5},
                "achievements": ["first_capot", 3],
                "unknown_future_key": 1,
            }
        )
    )
    mgr = StatisticsManager(path)
    stats = mgr.load_stats()

    assert stats.games_played == 7  # valid field kept
    assert stats.games_won == 0
    assert stats.capots_achieved == 0  # bool is not an int count
    assert stats.most_used_trump == Statistics().most_used_trump
    assert stats.difficulty_stats["hard"] == {"played": 3, "won": 0}
    assert stats.difficulty_stats["easy"] == {"played": 0, "won": 0}
    assert stats.difficulty_stats["nope"] == {"played": 0, "won": 0}
    assert stats.achievements == ["first_capot"]
    # Parseable file: not moved aside.
    assert not (tmp_path / "stats.json.bak").exists()

    mgr.update_stats_round(False, 80, "♠")  # used to TypeError on None
    assert mgr.load_stats().most_used_trump["♠"] == 1


def test_valid_stats_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    original = Statistics(games_played=3, games_won=2, achievements=["x"])
    original.most_used_trump["♥"] = 5
    StatisticsManager(path).save_stats(original)
    assert StatisticsManager(path).load_stats() == original


# ── save_stats ──────────────────────────────────────────────────────────────


def test_save_stats_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure mid-dump must leave the existing file intact and no tmp."""
    path = tmp_path / "stats.json"
    mgr = StatisticsManager(path)
    mgr.save_stats(Statistics(games_played=5))
    before = path.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("belote.stats.json.dump", boom)
    mgr.save_stats(Statistics(games_played=6))

    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["stats.json"]


def test_save_stats_creates_missing_dir(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "stats.json"
    StatisticsManager(path).save_stats(Statistics(games_played=1))
    assert json.loads(path.read_text())["games_played"] == 1


# ── theme selection ─────────────────────────────────────────────────────────


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX perms, non-root")
def test_theme_save_on_read_only_config_dir_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.themes import theme_manager

    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    target = ro / "belote" / "theme.json"  # parent mkdir would fail
    monkeypatch.setattr(theme_manager, "_get_config_path", lambda: target)
    original = theme_manager.current_name
    other = next(n for n in theme_manager.list_themes() if n != original)
    calls: list[str] = []
    monkeypatch.setattr(theme_manager, "_on_change_callbacks", [lambda: calls.append("cb")])
    try:
        theme_manager.set_current(other)  # used to raise PermissionError
        assert theme_manager.current_name == other
        assert calls == ["cb"]
    finally:
        ro.chmod(0o700)
        theme_manager._current_theme_name = original


def test_theme_callbacks_run_even_if_save_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.themes import theme_manager

    original = theme_manager.current_name
    other = next(n for n in theme_manager.list_themes() if n != original)
    calls: list[str] = []
    monkeypatch.setattr(theme_manager, "_on_change_callbacks", [lambda: calls.append("cb")])

    def boom() -> None:
        raise RuntimeError("save failed")

    monkeypatch.setattr(theme_manager, "save_selection", boom)
    try:
        with pytest.raises(RuntimeError):
            theme_manager.set_current(other)
        assert calls == ["cb"]  # caches were invalidated before the save
    finally:
        theme_manager._current_theme_name = original


def test_theme_save_writes_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.themes import theme_manager

    target = tmp_path / "belote" / "theme.json"
    monkeypatch.setattr(theme_manager, "_get_config_path", lambda: target)
    theme_manager.save_selection()
    assert json.loads(target.read_text()) == {"theme": theme_manager.current_name}
    assert [p.name for p in target.parent.iterdir()] == ["theme.json"]


# ── stats path ──────────────────────────────────────────────────────────────


def test_stats_path_honours_appdata_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import belote.config as config_mod
    import belote.paths as paths_mod

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(paths_mod, "_is_windows", lambda: True)
    assert config_mod.Config().stats_path == tmp_path / "belote" / "stats.json"


def test_stats_path_ignores_appdata_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import belote.config as config_mod

    if os.name == "nt":
        pytest.skip("POSIX-only behaviour")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert config_mod.Config().stats_path == tmp_path / "xdg" / "belote" / "stats.json"


def test_theme_config_path_honours_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-4.10.0 the theme file was hardcoded to ~/.config, ignoring
    XDG_CONFIG_HOME (and leaking the test suite into the real user config)."""
    from belote.themes import ThemeManager

    if os.name == "nt":
        pytest.skip("POSIX-only behaviour")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert ThemeManager()._get_config_path() == tmp_path / "belote" / "theme.json"


def test_stats_screen_lists_achievements() -> None:
    """Achievements were evaluated and persisted but never displayed."""
    from belote.achievements import ACHIEVEMENTS
    from belote.ansi import visible_len
    from belote.ui.announce import _achievement_lines

    first = ACHIEVEMENTS[0]
    lines = _achievement_lines([first.id])
    assert f"1/{len(ACHIEVEMENTS)}" in lines[0]
    body = "".join(lines[1:])
    assert f"★ {first.title}" in body
    assert all(f"☆ {a.title}" in body for a in ACHIEVEMENTS[1:])
    # Must fit the 80-col minimum terminal.
    assert all(visible_len(line) <= 80 for line in lines)


def test_theme_cycle_wraps_and_recovers_from_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.themes import THEMES, ThemeManager

    tm = ThemeManager()
    monkeypatch.setattr(tm, "_get_config_path", lambda: tmp_path / "theme.json")
    names = list(THEMES)
    tm.set_current(names[-1])
    assert tm.cycle() == names[0]
    tm._current_theme_name = "no-such-theme"
    assert tm.cycle() == names[0]


def test_update_stats_round_returns_new_unlocks_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlocks are returned to the caller (who shows the toast) exactly once."""
    from belote import stats as stats_mod

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    stats_mod._MANAGER._stats_cache = None
    monkeypatch.setattr(stats_mod._MANAGER, "_session_stats", stats_mod.SessionStats())
    try:
        first = stats_mod.update_stats_round(True, 252, "♠")
        assert "first_capot" in [a.id for a in first]
        again = stats_mod.update_stats_round(True, 252, "♠")
        assert "first_capot" not in [a.id for a in again]
    finally:
        stats_mod._MANAGER._stats_cache = None


def test_achievement_toast_lines_frame_the_text() -> None:
    from belote.ui.announce import achievement_toast_lines

    lines = achievement_toast_lines("Le Grand Chelem", "Score your first Capot.")
    assert len(lines) == 4
    assert len({len(line) for line in lines}) == 1  # rectangular box
    assert "ACHIEVEMENT UNLOCKED" in lines[1]
    assert "Le Grand Chelem — Score your first Capot." in lines[2]
