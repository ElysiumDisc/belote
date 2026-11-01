"""4.11.0 customisation: settings keys + back-compat, the Settings pickers
(live preview, locked items), Controls (rebindable keys), theme files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from belote import cosmetics
from belote import input as input_mod
from belote import settings as settings_mod
from belote.ansi import visible_len
from belote.input import Key, KeyEvent, char_event, typed
from belote.settings import Settings
from belote.themes import (
    COLOR_FIELDS,
    MAX_THEME_BYTES,
    THEMES,
    ThemeFileError,
    export_theme,
    import_theme,
    list_theme_files,
    parse_theme,
    theme_files_dir,
    theme_manager,
)
from belote.ui import customize, settings_menu
from tests.harness import TUI, isolate_dirs, raw_char, strip_ansi


@pytest.fixture(autouse=True)
def _restore_globals() -> Iterator[None]:
    theme = theme_manager.current_name
    themes = dict(THEMES)
    yield
    input_mod.set_bindings({})
    cosmetics.set_active(back=cosmetics.DEFAULT_BACK, frame=cosmetics.DEFAULT_FRAME)
    for key in set(THEMES) - set(themes):
        if theme_manager.current_name == key:
            theme_manager.set_current(theme)
        del THEMES[key]
    if theme_manager.current_name != theme:
        theme_manager.set_current(theme)


@pytest.fixture
def dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return isolate_dirs(monkeypatch, tmp_path)


@pytest.fixture
def saves(monkeypatch: pytest.MonkeyPatch) -> list[Settings]:
    out: list[Settings] = []
    monkeypatch.setattr(settings_mod, "save", out.append)
    return out


def _row(key: str) -> int:
    return [r.key for r in settings_menu.rows()].index(key)


# ── settings persistence ───────────────────────────────────────────────────


def test_new_settings_roundtrip(dirs: Path) -> None:
    s = Settings(card_back="damier", table_frame="minimal", keys={"help": "k", "undo": "u"})
    settings_mod.save(s)
    assert settings_mod.load() == s
    raw = json.loads(settings_mod.settings_path().read_text())
    assert raw["card_back"] == "damier" and raw["table_frame"] == "minimal"
    assert raw["keys"] == {"help": "k", "undo": "u"}


def test_old_settings_file_loads_with_defaults(dirs: Path) -> None:
    path = settings_mod.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"target": 1500, "speed": "fast", "animations": False}))
    s = settings_mod.load()
    assert (s.target, s.speed, s.animations) == (1500, "fast", False)
    assert (s.card_back, s.table_frame, s.keys) == ("classique", "art_nouveau", {})


@pytest.mark.parametrize(
    "extra",
    [
        {"card_back": "../../etc", "table_frame": 7, "keys": "q"},
        {"card_back": None, "keys": {"help": "p"}},  # reserved letter
        {"keys": {"help": "w"}},  # conflicts with Move up
        {"keys": {"help": "kk"}},
        {"keys": {"no_such_action": "k"}},  # unknown actions are dropped
    ],
)
def test_invalid_customisation_values_fall_back(dirs: Path, extra: dict[str, object]) -> None:
    path = settings_mod.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"speed": "fast", **extra}))
    s = settings_mod.load()
    assert s.speed == "fast"
    assert (s.card_back, s.table_frame, s.keys) == ("classique", "art_nouveau", {})


def test_apply_installs_bindings_and_survives_bad_ones() -> None:
    prev = settings_mod.current()
    try:
        settings_mod.apply(Settings(keys={"help": "k"}))
        assert char_event("k").key == Key.HELP
        settings_mod.apply(Settings(keys={"help": "p"}))  # invalid → defaults
        assert char_event("?").key == Key.HELP
        assert char_event("k").key == Key.CHAR
    finally:
        settings_mod.apply(prev)


# ── Settings screen ────────────────────────────────────────────────────────


def test_settings_rows_share_one_value_column() -> None:
    s = Settings()
    lines = settings_menu.settings_lines(s, -1)
    body = [strip_ansi(x) for x in lines[3 : 3 + len(settings_menu.rows()) + 1] if x.strip()]
    assert len({visible_len(x) for x in body}) == 1
    lt = [x.index("<") for x in body if "<" in x]
    assert len(set(lt)) == 1  # every "<" in the same column (Theme included)
    text = "\n".join(body)
    assert "Card back" in text and "Table frame" in text and "Controls" in text


def test_settings_preview_follows_selected_row() -> None:
    s = Settings(card_back="damier")
    back = "\n".join(settings_menu.settings_lines(s, _row("card_back")))
    assert "▚▚" in back
    frame = strip_ansi("\n".join(settings_menu.settings_lines(s, _row("table_frame"))))
    assert "◆" in frame
    assert "▚▚" not in "\n".join(settings_menu.settings_lines(s, 0))


def test_arrows_only_cycle_unlocked_backs(dirs: Path) -> None:
    s = Settings()
    seen = []
    for _ in range(4):
        settings_menu.change(s, "card_back", 1)
        seen.append(s.card_back)
    assert seen == ["damier", "rayures", "classique", "damier"]
    cosmetics._save_unlocked({"back:vague"})
    s.card_back = "rayures"
    settings_menu.change(s, "card_back", 1)
    assert s.card_back == "vague"
    settings_menu.change(s, "table_frame", -1)
    assert s.table_frame == "minimal"
    settings_menu.change(s, "controls", 1)  # action rows ignore ←/→
    settings_menu.change(s, "theme_files", 1)


def test_picker_selects_unlocked_and_refuses_locked(tui: TUI, saves: list[Settings]) -> None:
    s = Settings()
    # Enter on Card back → picker: down (Damier) Enter; down x2 (Tressé, locked) Enter; Esc; Esc.
    r = tui.reader(*["down"] * _row("card_back"), "enter", "down", "enter")
    r.push("down", "down", "enter", "esc", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.card_back == "damier"
    assert cosmetics.active_back().id == "damier"
    text = tui.text
    assert "CARD BACK" in text and "Damier selected" in text
    assert "Locked — Joueur Patient — Play 25 games. 0/25" in text
    assert saves == [s]


def test_frame_picker_after_unlock_announces_it(tui: TUI, saves: list[Settings]) -> None:
    from belote.achievements import ACHIEVEMENTS
    from belote.stats import Statistics

    stats = Statistics(achievements=[a.id for a in ACHIEVEMENTS])
    tui.monkeypatch.setattr(customize, "load_stats", lambda: stats)
    tui.monkeypatch.setattr(
        cosmetics, "check_unlocks", lambda st=None, real=cosmetics.check_unlocks: real(stats)
    )
    s = Settings()
    r = tui.reader(*["down"] * _row("table_frame"), "enter", "up", "enter", "esc", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.table_frame == "gilded"
    assert cosmetics.active_frame().id == "gilded"
    assert "Gilded selected" in tui.text


# ── keybindings ────────────────────────────────────────────────────────────


def test_default_bindings_match_the_historic_table() -> None:
    assert input_mod.current_bindings() == input_mod.DEFAULT_BINDINGS
    assert char_event("s") == KeyEvent(Key.DOWN, "s") and typed(char_event("S"), "s")
    assert char_event("z") == KeyEvent(Key.CHAR, "z")
    assert input_mod.key_label("quit") == "Q"


@pytest.mark.parametrize(
    ("action", "key", "fragment"),
    [
        ("help", "w", "already used by Move up"),
        ("help", "p", "reserved for Pass"),
        ("undo", "c", "reserved for Coinche"),
        ("up", "s", "reserved for Surcoinche"),
        ("quit", "z", "reserved for Undo"),
        ("help", "5", "quick select"),
        ("help", " ", "single letter"),
        ("help", "ab", "single letter"),
        ("help", "é", "single letter"),
        ("nope", "k", "Unknown action"),
    ],
)
def test_binding_conflicts(action: str, key: str, fragment: str) -> None:
    err = input_mod.check_binding(action, key, dict(input_mod.DEFAULT_BINDINGS))
    assert err is not None and fragment in err


def test_defaults_on_reserved_letters_are_allowed() -> None:
    d = dict(input_mod.DEFAULT_BINDINGS)
    assert input_mod.check_binding("down", "s", d) is None
    assert input_mod.check_binding("left", "A", d) is None
    assert input_mod.check_binding("undo", "z", d) is None


def test_remap_keeps_typed_chars_and_frees_old_keys() -> None:
    input_mod.set_bindings({"help": "k", "up": "i", "overlay": "j"})
    assert char_event("k") == KeyEvent(Key.HELP, "k")
    assert char_event("K") == KeyEvent(Key.HELP, "K")
    assert char_event("i") == KeyEvent(Key.UP, "i")
    assert char_event("?") == KeyEvent(Key.CHAR, "?")
    assert char_event("w") == KeyEvent(Key.CHAR, "w")
    assert input_mod.CHAR_ALIASES["j"] is Key.OVERLAY
    assert input_mod.current_bindings()["help"] == "k"


def test_undo_remap_reaches_the_prompts() -> None:
    from belote.ui.prompts import _bid_quick_key, _card_quick_key

    input_mod.set_bindings({"undo": "u"})
    ev = char_event("u")
    assert ev == KeyEvent(Key.CHAR, "z")
    assert ev.char is not None and _card_quick_key(ev.char, (), ()) == "UNDO"
    assert _bid_quick_key(ev.char, []) == "UNDO"
    assert char_event("z").key == Key.UNKNOWN  # no longer undoes
    assert input_mod.key_label("undo") == "U"
    # The fixed bid letters still arrive as plain characters.
    assert [char_event(c).key for c in "pxnc"] == [Key.CHAR] * 4


def test_invalid_set_bindings_changes_nothing() -> None:
    input_mod.set_bindings({"help": "k"})
    with pytest.raises(ValueError):
        input_mod.set_bindings({"help": "q"})
    assert char_event("k").key == Key.HELP and char_event("q").key == Key.QUIT


def test_raw_capture_bypasses_aliases() -> None:
    with input_mod.raw_capture():
        assert char_event("w") == KeyEvent(Key.CHAR, "w")
    assert char_event("w").key == Key.UP


def test_controls_screen_rebinds_rejects_and_resets(tui: TUI, saves: list[Settings]) -> None:
    s = Settings()
    r = tui.reader(*["down"] * _row("controls"), "enter")
    r.push("enter", raw_char("k"))  # Help → K
    r.push("down", "enter", raw_char("p"))  # Quit → P: reserved
    r.push("enter", raw_char("k"))  # Quit → K: used by Help
    r.push("enter", "left")  # arrows can't be bound
    r.push("enter", "esc")  # cancelled
    r.push("esc", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    assert s.keys == {"help": "k"}
    assert char_event("k").key == Key.HELP
    text = tui.text
    assert "CONTROLS" in text and "Help → K" in text
    assert "P is reserved for Pass (bidding)" in text
    assert "K is already used by Help" in text
    assert "can't be bound" in text and "Cancelled" in text
    assert saves == [s] and settings_mod.load() == Settings()  # save is stubbed

    n = len(input_mod.BINDINGS)
    r2 = tui.reader(*["down"] * n, "enter", "esc")  # Reset to defaults
    customize.show_controls(r2.as_reader(), s)
    assert s.keys == {} and char_event("?").key == Key.HELP
    assert "All keys reset to defaults" in tui.text


def test_controls_persist_through_settings_file(dirs: Path) -> None:
    s = Settings()
    assert customize.rebind(s, "undo", "U") is None
    assert customize.rebind(s, "sort", "u") == "U is already used by Undo"
    settings_mod.save(s)
    loaded = settings_mod.load()
    assert loaded.keys == {"undo": "u"}
    settings_mod.apply(Settings())


# ── theme files ────────────────────────────────────────────────────────────


def _theme_doc(**over: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "format": "belote-theme",
        "version": 1,
        "name": "Mine",
        "colors": dict.fromkeys(COLOR_FIELDS, "#102030"),
    }
    doc.update(over)
    return doc


def _write(name: str, content: str | bytes) -> Path:
    folder = theme_files_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    return path


def test_export_import_roundtrip(dirs: Path) -> None:
    path = export_theme("sunset_magma")
    assert path == theme_files_dir() / "sunset_magma.json"
    key = import_theme(path)
    assert key == "custom:sunset_magma"
    src, got = THEMES["sunset_magma"], THEMES[key]
    assert all(getattr(src, f) == getattr(got, f) for f in COLOR_FIELDS)
    assert got.name == src.name
    assert list_theme_files() == [path]


def test_rgb_lists_are_accepted(dirs: Path) -> None:
    doc = _theme_doc(colors={k: [1, 2, 3] for k in COLOR_FIELDS})
    theme = parse_theme(json.dumps(doc).encode())
    assert theme.felt_bg == (1, 2, 3)


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        (b"\xff\xfe garbage", "not valid UTF-8 JSON"),
        (b"{not json", "not valid UTF-8 JSON"),
        (b"[" * 100_000, "larger than"),
        (b"[" * 4000 + b"]" * 4000, "top level"),  # deep nesting: parsed safely
        (b"[1, 2]", "top level"),
        (json.dumps(_theme_doc(extra=1)).encode(), "unknown field"),
        (json.dumps(_theme_doc(format="evil")).encode(), '"format"'),
        (json.dumps(_theme_doc(version=99)).encode(), "unsupported version"),
        (json.dumps(_theme_doc(colors=[])).encode(), '"colors" must be an object'),
        (json.dumps(_theme_doc(name="\x1b[2J pwned")).encode(), '"name"'),
        (json.dumps(_theme_doc(name="x" * 40)).encode(), '"name"'),
        (json.dumps(_theme_doc(name=5)).encode(), '"name"'),
    ],
)
def test_parse_rejects_malformed_documents(raw: bytes, fragment: str) -> None:
    with pytest.raises(ThemeFileError) as exc:
        parse_theme(raw)
    assert fragment in str(exc.value)


@pytest.mark.parametrize(
    "bad",
    ["#12345", "#gggggg", "red", [0, 0], [0, 0, 256], [-1, 0, 0], [True, 0, 0], [1.5, 0, 0], None],
)
def test_parse_rejects_bad_colours(bad: object) -> None:
    colors: dict[str, object] = dict.fromkeys(COLOR_FIELDS, "#000000")
    colors["red_fg"] = bad
    with pytest.raises(ThemeFileError, match="red_fg"):
        parse_theme(json.dumps(_theme_doc(colors=colors)).encode())


def test_parse_rejects_unknown_and_missing_colour_keys() -> None:
    colors: dict[str, object] = dict.fromkeys(COLOR_FIELDS, "#000000")
    with pytest.raises(ThemeFileError, match="unknown colour"):
        parse_theme(json.dumps(_theme_doc(colors={**colors, "evil\x1b": "#000000"})).encode())
    del colors["gold_fg"]
    with pytest.raises(ThemeFileError, match="missing colour"):
        parse_theme(json.dumps(_theme_doc(colors=colors)).encode())


def test_import_refuses_unsafe_paths_and_big_files(dirs: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_theme_doc()))
    folder = theme_files_dir()
    folder.mkdir(parents=True)
    for path in (
        folder / ".." / "outside.json",
        folder / "../../outside.json",
        outside,
        folder / "bad name.json",
        folder / "x.txt",
    ):
        with pytest.raises(ThemeFileError):
            import_theme(path)
    link = folder / "link.json"
    link.symlink_to(outside)
    with pytest.raises(ThemeFileError, match="inside the themes folder"):
        import_theme(link)
    big = _write("big.json", b" " * (MAX_THEME_BYTES + 1))
    with pytest.raises(ThemeFileError, match="larger than"):
        import_theme(big)
    with pytest.raises(ThemeFileError, match="could not be read"):
        import_theme(folder / "missing.json")
    assert [p.name for p in list_theme_files()] == ["big.json"]  # symlink / bad names hidden


def test_custom_theme_selection_survives_restart(dirs: Path) -> None:
    from belote.themes import ThemeManager

    path = _write("mine.json", json.dumps(_theme_doc()))
    key = import_theme(path)
    theme_manager.set_current(key)
    del THEMES[key]  # a fresh process has only the built-ins
    tm = ThemeManager()
    tm._current_theme_name = "classic_green"
    tm.load_selection()
    assert tm.current_name == key and THEMES[key].name == "Mine"
    del THEMES[key]
    path.write_text("{broken")
    tm._current_theme_name = "classic_green"
    tm.load_selection()  # file no longer valid → stays on the default
    assert tm.current_name == "classic_green"


def test_theme_files_screen(tui: TUI, saves: list[Settings]) -> None:
    _write("aaa_bad.json", "[1, 2, 3]")
    _write("zzz_good.json", json.dumps(_theme_doc(name="Good One")))
    s = Settings()
    r = tui.reader(*["down"] * _row("theme_files"), "enter")
    r.push("enter")  # export the current theme
    r.push("down", "enter")  # import aaa_bad.json → error
    r.push("down", "down", "enter")  # import zzz_good.json (after the export appeared)
    r.push("esc", "esc")
    settings_menu.show_settings(r.as_reader(), s)
    text = tui.text
    assert "THEME FILES" in text and "Exported to classic_green.json" in text
    assert "Can't import aaa_bad.json: top level must be a JSON object" in text
    assert "Imported “Good One” — now active" in text
    assert theme_manager.current_name == "custom:zzz_good"
    assert (theme_files_dir() / "classic_green.json").is_file()


def test_theme_files_screen_with_empty_folder(tui: TUI) -> None:
    r = tui.reader("down", "enter")
    customize.show_theme_files(r.as_reader())
    assert "no theme files to import yet" in tui.text


def test_export_failure_is_reported(tui: TUI) -> None:
    def fail(_key: str) -> Path:
        raise PermissionError(13, "Permission denied")

    tui.monkeypatch.setattr(customize, "export_theme", fail)
    assert customize.export_current() == ("Export failed: Permission denied", False)
