"""4.11.0 Boss Rush / Challenge Seed: setup screen, the run it builds, and how
the normal run loop treats a challenge run."""

from __future__ import annotations

from typing import Any

import pytest

from belote.belatro import main as bmain
from belote.belatro.core.run_state import BelAtroRun
from belote.belatro.progression.save import Profile
from belote.belatro.run.decks import COMPLICE_UNLOCK_ID
from belote.belatro.ui.boss_rush import boss_rush_lines, new_setup, show_boss_rush
from belote.belatro.ui.menu import BelAtroMainMenu
from tests.harness import strip_ansi


def test_defaults_build_a_random_boss_rush_from_ante_1(tui: Any) -> None:
    run = show_boss_rush(tui.reader("enter"), Profile())
    assert isinstance(run, BelAtroRun)
    assert run.challenge and run.boss_rush and run.challenge_boss_id is None
    assert run.ante_number == 1 and run.deck_id == "classique"
    assert "BOSS RUSH" in tui.text


def test_choose_ante_boss_deck_seed_and_toggle(tui: Any) -> None:
    # ante 1 → 8 (wraps) | boss: Random → 2nd boss | deck → L'Aristocrate |
    # seed "42" → x ignored → ← deletes → "4" → "47" | every blind a boss: No
    script = [
        "left",
        "down",
        "right",
        "right",
        "down",
        "right",
        "down",
        "4",
        "2",
        "x",
        "left",
        "7",
        "down",
        "left",
        "enter",
    ]
    run = show_boss_rush(tui.reader(*script), Profile())
    assert run is not None
    from belote.belatro.run.boss import ALL_BOSS_MODIFIERS

    assert run.ante_number == 8
    assert run.challenge_boss_id == ALL_BOSS_MODIFIERS[1].id
    assert run.deck_id == "aristocrate"
    assert run.seed == 47
    assert run.boss_rush is False


def test_esc_backs_out(tui: Any) -> None:
    assert show_boss_rush(tui.reader("down", "esc"), Profile()) is None


def test_only_unlocked_decks_are_offered() -> None:
    assert all(d.id != "complice" for d in new_setup(Profile()).decks)
    profile = Profile()
    profile.unlock(COMPLICE_UNLOCK_ID)
    assert any(d.id == "complice" for d in new_setup(profile).decks)


@pytest.mark.parametrize(("cols", "rows"), [(80, 32), (100, 38)])
def test_setup_screen_fits(cols: int, rows: int) -> None:
    setup = new_setup(Profile())
    setup.boss_idx = max(range(len(setup.boss_ids)), key=lambda i: len(str(setup.boss_ids[i])))
    lines = boss_rush_lines(setup, cols)
    assert len(lines) <= rows
    assert all(len(strip_ansi(line)) <= cols for line in lines)


def test_menu_entry_returns_the_challenge_run(tui: Any) -> None:
    menu = BelAtroMainMenu(tui.reader("down", "down", "enter", "enter"), Profile())
    run = menu.run()
    assert isinstance(run, BelAtroRun) and run.challenge


def test_pinned_boss_and_every_blind_boss(tui: Any) -> None:
    run = BelAtroRun(seed=2, challenge=True, boss_rush=True, challenge_boss_id="le_mime")
    for blind in (0, 1, 2):
        run.blind_index = blind
        boss = bmain.BelAtroGame._pick_boss(run, tui.reader(default=None))
        assert boss is not None and boss.id == "le_mime"


def test_challenge_runs_skip_run_milestones(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    game = bmain.BelAtroGame()
    game.reader = tui.reader(default=None)
    game.run = BelAtroRun(seed=1, ante_number=8, challenge=True, profile=game.profile)
    game.run.blind_index = 2
    monkeypatch.setattr(game, "_play_blind", lambda: None)

    class _NoShop:
        def __init__(self, *a: object) -> None:
            pass

        def run(self) -> None:
            pass

    monkeypatch.setattr(bmain, "ShopScreen", _NoShop)
    calls: list[str] = []
    monkeypatch.setattr(game.unlock_tracker, "notify_run_won", lambda: calls.append("won"))
    monkeypatch.setattr(game.unlock_tracker, "check_ante_unlocks", lambda n: calls.append("ante"))
    game._run_loop()
    assert game.run.run_won and calls == []
    assert "Endless" not in tui.text
