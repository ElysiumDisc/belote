"""5.0.0 Le Carnet de Parties on screen: the Statistics section and the
game-over verdict line."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from belote.game import new_game


def test_statistics_screen_lists_the_carnet(tui: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    import belote.ui.announce  # noqa: F401 — `belote.ui.announce` is shadowed by a function
    from belote import stats as stats_mod

    announce_mod = sys.modules["belote.ui.announce"]

    tui.resize(120, 60)
    stats_mod._MANAGER._stats_cache = stats_mod.Statistics(
        recent_games=[
            {
                "date": "2026-11-02",
                "won": False,
                "ns": 912,
                "ew": 1004,
                "rounds": 9,
                "difficulty": "hard",
                "verdict": "You chutéed on a 92 vs 94 — brutal.",
            }
        ]
    )
    try:
        announce_mod.show_stats(tui.reader("q"))
    finally:
        stats_mod._MANAGER._stats_cache = None
    assert "Le Carnet de Parties" in tui.text
    assert "L 912–1004  You chutéed on a 92 vs 94 — brutal." in tui.text


def test_game_over_screen_shows_the_verdict(tui: Any) -> None:
    from belote import main as main_mod

    state = replace(new_game(), team_scores=(1010, 640))
    main_mod._game_over_screen(state, tui.reader("enter"), "A solid win, 1010 to 640.")
    assert "Carnet: A solid win, 1010 to 640." in tui.text


def test_record_game_over_returns_and_stores_the_verdict(
    tui: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from belote import main as main_mod
    from belote.game import Seat

    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(main_mod, "update_stats_game", lambda **_k: [])
    monkeypatch.setattr(main_mod, "add_recent_game", saved.append)
    monkeypatch.setattr(main_mod, "flush_stats", lambda: None)
    state = replace(new_game(), team_scores=(1003, 987))
    verdict = main_mod._record_game_over(
        state, dict.fromkeys((Seat.EAST, Seat.NORTH, Seat.WEST), "medium"), 1000, tui.reader()
    )
    assert verdict == "Photo finish: 1003 to 987."
    assert saved[0]["won"] is True and saved[0]["difficulty"] == "medium"
