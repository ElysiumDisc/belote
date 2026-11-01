"""4.11.0 cosmetics: card backs, table frames, unlock milestones + providers,
persistence, toasts and the Statistics "Unlocks" section."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from belote import cosmetics
from belote.ansi import PALETTE_FIELDS, RESET, card_back_bg, visible_len
from belote.context import TERMINAL
from belote.cosmetics import CardBack, TableFrame
from belote.stats import Statistics
from belote.ui import cards
from belote.ui.layout import COMPACT, SPACIOUS, STANDARD
from tests.harness import TUI, isolate_dirs, strip_ansi

LAYOUTS = (COMPACT, STANDARD, SPACIOUS)


@pytest.fixture(autouse=True)
def _reset_cosmetics() -> Iterator[None]:
    providers = dict(cosmetics._PROVIDERS)
    yield
    cosmetics._PROVIDERS.clear()
    cosmetics._PROVIDERS.update(providers)
    cosmetics.set_active(back=cosmetics.DEFAULT_BACK, frame=cosmetics.DEFAULT_FRAME)


@pytest.fixture
def dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return isolate_dirs(monkeypatch, tmp_path)


def _flush_render_caches() -> None:
    from belote.ui.render import clear_card_cache

    clear_card_cache()


# ── default rendering is unchanged ─────────────────────────────────────────


def _legacy_back(has_utf8: bool, card_w: int, card_h: int) -> list[str]:
    """The pre-4.11 `_card_back` body, verbatim."""
    inner_w, inner_h = card_w - 2, card_h - 2
    fill = "░▒▓▒░" if has_utf8 else "XXXXX"
    pattern_row = (" " + fill + " ").center(inner_w)[:inner_w].ljust(inner_w)
    b_tl, b_tr, b_bl, b_br, b_h, b_v = (
        ("╔", "╗", "╚", "╝", "═", "║") if has_utf8 else ("+", "+", "+", "+", "-", "|")
    )
    res = [f"{card_back_bg()}{b_tl}{b_h * inner_w}{b_tr}{RESET}"]
    res += [f"{card_back_bg()}{b_v}{pattern_row}{b_v}{RESET}"] * inner_h
    res.append(f"{card_back_bg()}{b_bl}{b_h * inner_w}{b_br}{RESET}")
    return res


@pytest.mark.parametrize("utf8", [True, False])
@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.name)
def test_default_back_is_byte_identical_to_legacy(
    utf8: bool, layout: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TERMINAL, "has_utf8", utf8)
    w, h = layout.card_w, layout.card_h  # type: ignore[attr-defined]
    assert cards._card_back("classic_green", utf8, w, h) == _legacy_back(utf8, w, h)
    chip = "▓▓" if utf8 else "[]"
    assert cards._card_back_small() == f"{card_back_bg()}{chip}{RESET}"


def test_default_frame_matches_legacy_art_nouveau() -> None:
    from belote.ui import table

    inner = ["x" * 20, "y" * 20]
    rows = table.frame_rows(cosmetics.TABLE_FRAMES["art_nouveau"], inner, 20)
    assert rows is not None
    plain = [strip_ansi(r) for r in rows]
    assert plain[0] == "╔" + "══════◆══════◆══════" + "╗"
    assert plain[-1] == "╚" + "══════◆══════◆══════" + "╝"
    assert plain[1] == "║" + "x" * 20 + "║"


# ── every back / frame renders correctly ────────────────────────────────────


@pytest.mark.parametrize("utf8", [True, False])
@pytest.mark.parametrize("layout", LAYOUTS, ids=lambda lay: lay.name)
@pytest.mark.parametrize("back_id", list(cosmetics.CARD_BACKS))
def test_every_back_renders_at_every_size(
    back_id: str, layout: object, utf8: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TERMINAL, "has_utf8", utf8)
    w, h = layout.card_w, layout.card_h  # type: ignore[attr-defined]
    rows = cards.card_back_lines(layout, back_id)  # type: ignore[arg-type]
    assert len(rows) == h
    assert all(visible_len(r) == w for r in rows)
    assert all(r.endswith(RESET) for r in rows)
    chip = cards.card_back_chip(back_id)
    assert visible_len(chip) == 2
    if not utf8:
        assert all(strip_ansi(r).isascii() for r in rows)
        assert strip_ansi(chip).isascii()


def test_backs_are_distinct_and_ascii_glyph_data_is_ascii() -> None:
    backs = list(cosmetics.CARD_BACKS.values())
    assert len(backs) >= 10
    assert len({b.pattern for b in backs}) == len(backs)
    for b in backs:
        assert all("".join(b.pattern_ascii).isascii() for _ in (0,))
        assert b.small_ascii.isascii() and len(b.small_ascii) == 2
        assert visible_len(b.small) == 2
    free = [b for b in backs if b.milestone is None]
    assert [b.id for b in free] == ["classique", "damier", "rayures"]


def test_colour_refs_name_real_palette_fields() -> None:
    for b in cosmetics.CARD_BACKS.values():
        if isinstance(b.fg, str):
            assert b.fg in PALETTE_FIELDS and b.fg.endswith("_fg")
        if isinstance(b.bg, str):
            assert b.bg in PALETTE_FIELDS and b.bg.endswith("_bg")
        for rgb in (b.fg, b.bg):
            if isinstance(rgb, tuple):
                assert len(rgb) == 3 and all(0 <= c <= 255 for c in rgb)
    for f in cosmetics.TABLE_FRAMES.values():
        assert f.fg in PALETTE_FIELDS
    for item in cosmetics.all_items():
        assert item.milestone is None or item.milestone in cosmetics.MILESTONES


def test_backs_respect_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote import ansi

    monkeypatch.setenv("NO_COLOR", "1")
    ansi._refresh_no_color_from_env()
    _flush_render_caches()
    try:
        for back_id in cosmetics.CARD_BACKS:
            text = "".join(cards.card_back_lines(STANDARD, back_id)) + cards.card_back_chip(back_id)
            assert "38;2;" not in text and "48;2;" not in text
    finally:
        monkeypatch.delenv("NO_COLOR")
        ansi._refresh_no_color_from_env()
        _flush_render_caches()


@pytest.mark.parametrize("utf8", [True, False])
@pytest.mark.parametrize("frame_id", list(cosmetics.TABLE_FRAMES))
def test_every_frame_wraps_the_mat(
    frame_id: str, utf8: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.ui import table

    monkeypatch.setattr(TERMINAL, "has_utf8", utf8)
    cosmetics.set_active(frame=frame_id)
    rows = table._render_trick_mat_framed({}, 60, STANDARD)
    bare = table._render_trick_mat({}, 60, STANDARD)
    frame = cosmetics.TABLE_FRAMES[frame_id]
    if not utf8 and frame.glyphs_ascii is None:
        assert rows == bare  # Art Nouveau: no frame without UTF-8 (unchanged)
    else:
        assert len(rows) == len(bare) + 2
        assert all(visible_len(r) == 60 for r in rows)
        if not utf8:
            assert all(strip_ansi(r).isascii() for r in (rows[0], rows[-1]))
    preview = table.frame_preview(frame, 24, 5)
    assert len(preview) in (3, 5) and all(visible_len(r) in (22, 24) for r in preview)


def test_set_active_drives_the_render_cache_and_falls_back() -> None:
    cosmetics.set_active(back="damier", frame="minimal")
    assert cards._cached_back.id == "damier" and cards._cached_frame.id == "minimal"
    assert "▚▚" in cards._card_back_small()
    cosmetics.set_active(back="no-such-back", frame="nope")
    assert cosmetics.active_back().id == "classique"
    assert cosmetics.active_frame().id == "art_nouveau"


def test_settings_apply_pushes_cosmetics() -> None:
    from belote import settings as settings_mod

    prev = settings_mod.current()
    try:
        settings_mod.apply(settings_mod.Settings(card_back="vague", table_frame="gilded"))
        assert cosmetics.active_back().id == "vague"
        assert cosmetics.active_frame().id == "gilded"
    finally:
        settings_mod.apply(prev)
    assert cosmetics.active_back().id == "classique"


def test_full_frame_with_other_cosmetics_keeps_the_geometry(tui: TUI) -> None:
    """Non-default cosmetics change glyphs/colours only: same rows, same widths."""
    import random

    from belote.deck import Suit
    from belote.game import Phase, Seat, new_game, replace, start_round
    from belote.ui.render import render

    state = start_round(new_game(), random.Random(42))
    state = replace(state, phase=Phase.PLAYING, trump=Suit.SPADES, taker=Seat.SOUTH)

    def geometry(frame: str) -> list[int]:
        return [visible_len(row) for row in frame.split("\r\n")]

    base = render(state, 0)
    for back, frame in (("vague", "gilded"), ("neon_joker", "minimal")):
        cosmetics.set_active(back=back, frame=frame)
        out = render(state, 0)
        assert out != base
        assert geometry(out) == geometry(base)
        assert cosmetics.CARD_BACKS[back].small in strip_ansi(out)
    cosmetics.set_active(back="classique", frame="art_nouveau")
    assert render(state, 0) == base


# ── milestones, providers, persistence ─────────────────────────────────────


def test_progress_and_check_unlocks_persist_once(dirs: Path) -> None:
    stats = Statistics(games_played=12)
    m = cosmetics.MILESTONES["joueur_patient"]
    assert cosmetics.progress_of(m, stats) == (12, 25)
    assert cosmetics.check_unlocks(stats) == []
    stats.games_played = 30
    assert cosmetics.progress_of(m, stats) == (25, 25)  # capped
    new = cosmetics.check_unlocks(stats)
    assert [u.item.id for u in new] == ["tresse"]
    assert cosmetics.check_unlocks(stats) == []  # announced exactly once
    data = json.loads((dirs / "data" / "belote" / "cosmetics.json").read_text())
    assert data == {"version": 1, "unlocked": ["back:tresse"]}
    assert cosmetics.is_unlocked(cosmetics.CARD_BACKS["tresse"])
    assert "tresse" in cosmetics.unlocked_ids(CardBack)
    # Earned stays earned even if the stats are reset.
    assert cosmetics.check_unlocks(Statistics()) == []
    assert "tresse" in cosmetics.unlocked_ids(CardBack)


def test_every_core_milestone_unlocks_its_item(dirs: Path) -> None:
    from belote.achievements import ACHIEVEMENTS

    stats = Statistics(
        games_played=25,
        games_won=10,
        capots_achieved=10,
        total_rounds=250,
        achievements=[a.id for a in ACHIEVEMENTS],
    )
    stats.difficulty_stats["hard"]["won"] = 1
    got = {u.item.key for u in cosmetics.check_unlocks(stats)}
    assert got == {
        "back:tresse",
        "back:royal",
        "back:grand_chelem",
        "back:laurier",
        "back:vague",
        "frame:gilded",
    }
    assert set(cosmetics.unlocked_ids(TableFrame)) == {"art_nouveau", "minimal", "gilded"}


@pytest.mark.parametrize("content", ["{oops", "[]", '{"unlocked": 3}', '{"unlocked": [1, "x"]}'])
def test_corrupt_unlock_file_reads_as_nothing(dirs: Path, content: str) -> None:
    path = cosmetics.unlocks_path()
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert cosmetics.load_unlocked() <= {"x"}


def test_unlock_toast_shape(dirs: Path) -> None:
    from belote.ui.announce import achievement_toast_lines

    (toast,) = cosmetics.unlock_toasts(Statistics(capots_achieved=10))
    assert toast.id == "cosmetic:back:grand_chelem"
    assert toast.title == "Grand Chelem"
    assert toast.description == "Capot Collector: Score 10 Capots."
    assert toast.headline == "★ CARD BACK UNLOCKED ★"
    lines = achievement_toast_lines(toast.title, toast.description, toast.headline)
    assert "CARD BACK UNLOCKED" in lines[1] and len({len(x) for x in lines}) == 1


def test_stats_update_returns_cosmetic_unlocks(dirs: Path) -> None:
    from belote.stats import StatisticsManager

    mgr = StatisticsManager(dirs / "stats.json")
    stats = mgr.load_stats()
    stats.games_played = 24
    unlocked = mgr.update_stats_game(won=False, num_rounds=5, difficulty="medium")
    assert "cosmetic:back:tresse" in [a.id for a in unlocked]
    again = mgr.update_stats_game(won=False, num_rounds=5, difficulty="medium")
    assert not [a for a in again if a.id.startswith("cosmetic:")]
    for _ in range(9):
        mgr.update_stats_round(True, 252, "♠")
    capots = mgr.update_stats_round(True, 252, "♠")
    assert "cosmetic:back:grand_chelem" in [a.id for a in capots]


def test_stats_update_survives_a_broken_cosmetics_check(
    dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote.stats import StatisticsManager

    def boom(_stats: object = None) -> list[object]:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cosmetics, "unlock_toasts", boom)
    mgr = StatisticsManager(dirs / "stats.json")
    assert mgr.update_stats_game(won=True, num_rounds=3, difficulty="hard")[0].id == "win_hard"


def test_achievement_toast_shows_cosmetic_heading(tui: TUI) -> None:
    from belote.ui.announce import achievement_toast

    (toast,) = cosmetics.unlock_toasts(Statistics(total_rounds=300))
    achievement_toast(toast, None, hold=0)
    assert "CARD BACK UNLOCKED" in tui.text and "Vague" in tui.text


def test_provider_hook_with_fake_provider(dirs: Path) -> None:
    cosmetics._PROVIDERS.pop("l_insider", None)
    m = cosmetics.MILESTONES["l_insider"]
    assert m.progress is None
    assert cosmetics.progress_of(m, Statistics()) is None  # no provider: unavailable
    assert cosmetics.check_unlocks(Statistics()) == []

    calls: list[int] = []

    def fake() -> tuple[int, int]:
        calls.append(1)
        return (1, 1)

    cosmetics.register_unlock_provider("l_insider", fake)  # restored by the fixture
    assert [u.item.id for u in cosmetics.check_unlocks(Statistics())] == ["neon_joker"]
    cosmetics.check_unlocks(Statistics())
    assert len(calls) == 1  # earned items are no longer evaluated


def test_provider_errors_and_bad_ids(dirs: Path) -> None:
    with pytest.raises(ValueError):
        cosmetics.register_unlock_provider("joueur_patient", lambda: (1, 1))
    with pytest.raises(ValueError):
        cosmetics.register_unlock_provider("no_such", lambda: (1, 1))

    def broken() -> tuple[int, int]:
        raise OSError("profile unreadable")

    cosmetics._PROVIDERS["habitue_du_jour"] = broken
    assert cosmetics.progress_of(cosmetics.MILESTONES["habitue_du_jour"], Statistics()) is None
    assert cosmetics.check_unlocks(Statistics()) == []


def test_belatro_registers_its_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro import integration

    monkeypatch.setattr(integration, "_installed", False)
    cosmetics._PROVIDERS.clear()
    integration.install()
    assert cosmetics._PROVIDERS["l_insider"] is integration.insider_progress
    assert cosmetics._PROVIDERS["habitue_du_jour"] is integration.daily_days_progress


def test_belatro_providers_read_profile_and_daily_store(dirs: Path) -> None:
    from belote.belatro import integration
    from belote.belatro.progression.save import Profile, SaveManager

    assert integration.insider_progress() == (0, 1)
    assert integration.daily_days_progress() == (0, 5)
    profile = Profile()
    profile.stats["runs_won"] = 2
    SaveManager().save_profile(profile)
    store = {
        "2026-10-01": {"attempts": 1, "best": {}},
        "2026-10-02": {"attempts": 3, "best": {}},
        "2026-10-03": {"attempts": 0},
        "junk": "x",
    }
    (dirs / "data" / "belote" / "daily.json").write_text(json.dumps(store))
    assert integration.insider_progress() == (2, 1)
    assert integration.daily_days_progress() == (2, 5)


# ── Statistics screen ──────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [(80, 32), (100, 38), (120, 40)])
def test_stats_screen_fits_and_scrolls(tui: TUI, size: tuple[int, int]) -> None:
    from belote import stats as stats_mod
    from belote.ui.announce import show_stats

    tui.resize(*size)
    stats_mod._MANAGER._stats_cache = None
    try:
        r = tui.reader(*["down"] * 60, "right", "left", "enter")
        show_stats(r)
    finally:
        stats_mod._MANAGER._stats_cache = None
    frames = tui.screen.frames()
    assert frames
    for frame in frames:
        rows = frame.split("\r\n")
        assert len(rows) <= size[1]
        assert "GLOBAL STATISTICS" in strip_ansi(rows[0])  # pinned title
        assert all(visible_len(row) <= size[0] for row in rows)
    text = strip_ansi("".join(frames))
    assert "Unlocks: 5/13" in text
    assert "Tressé" in text and "Gilded" in text and "THIS SESSION" in text
    assert r.exhausted


def test_unlock_lines_progress_and_new_marker(dirs: Path) -> None:
    from belote.ui.customize import unlock_lines

    stats = Statistics(games_played=12)
    text = strip_ansi("\n".join(unlock_lines(stats, {"back:damier"})))
    assert re.search(r"✓ Damier NEW", text)
    assert "Tressé" in text and "Play 25 games. 12/25" in text
    assert "✓ Art Nouveau" in text and "Earn every Classic achievement. 0/6" in text
