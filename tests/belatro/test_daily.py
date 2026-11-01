"""Daily Challenge (belatro/daily.py)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from belote.belatro import daily
from belote.belatro.daily import DailyResult

DAY = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def _data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


def test_seed_is_stable_per_day_and_differs_between_days() -> None:
    assert daily.daily_seed(DAY) == daily.daily_seed(date(2026, 11, 1))
    assert daily.daily_seed(DAY) != daily.daily_seed(date(2026, 11, 2))
    assert 0 <= daily.daily_seed(DAY) < 2**32
    assert daily.daily_number(date(2026, 1, 1)) == 1


def test_seed_code_is_short_and_unambiguous() -> None:
    code = daily.seed_code(daily.daily_seed(DAY))
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{3}", code)
    assert daily.seed_code(0) == "0000-000"


def test_same_day_runs_are_identical() -> None:
    a, b = daily.new_daily_run(DAY), daily.new_daily_run(DAY)
    assert a.seed == b.seed and a.daily == "2026-11-01" and a.deck_id == "classique"
    assert [a._get_rng().random() for _ in range(5)] == [b._get_rng().random() for _ in range(5)]


def test_record_keeps_the_best_and_counts_attempts() -> None:
    assert daily.best_for(DAY) == (None, 0)
    assert daily.record(DAY, DailyResult(won=False, ante=2, blind=1, score=900)) is True
    assert daily.record(DAY, DailyResult(won=False, ante=1, blind=2, score=5000)) is False
    assert daily.record(DAY, DailyResult(won=False, ante=3, blind=0, score=100)) is True
    best, attempts = daily.best_for(DAY)
    assert attempts == 3
    assert best == DailyResult(won=False, ante=3, blind=0, score=100)
    assert daily.best_for(date(2026, 11, 2)) == (None, 0)


def test_intro_lines_show_number_code_and_best() -> None:
    joined = "\n".join(daily.intro_lines(DAY))
    assert f"#{daily.daily_number(DAY)}" in joined
    assert daily.seed_code(daily.daily_seed(DAY)) in joined
    assert "Not played yet" in joined
    daily.record(DAY, DailyResult(won=True, ante=8, blind=2, score=12345))
    assert "Cleared all 8 antes · 12,345 chips" in "\n".join(daily.intro_lines(DAY))


def test_daily_shop_pool_ignores_the_players_unlocks() -> None:
    """With the starter pool, a veteran (everything unlocked) gets exactly the
    shop a brand-new profile gets for the same seed — and not the shop their
    own unlocks would produce."""
    from belote.belatro.items.registry import registry
    from belote.belatro.progression.save import Profile
    from belote.belatro.run.shop import Shop

    veteran = Profile()
    veteran.unlocked_ids.extend(j for j in registry.jokers if j not in veteran.unlocked_ids)
    veteran.unlocked_ids.extend(v for v in registry.vouchers if v not in veteran.unlocked_ids)

    def shops(profile: Profile, pool: Profile | None, n: int = 12) -> list[list[str]]:
        run = daily.new_daily_run(DAY)
        shop = Shop(run, profile, pool=pool)
        out = []
        for _ in range(n):
            shop.generate_inventory()
            out.append([type(item).__name__ for item in shop.inventory])
        return out

    assert shops(veteran, Profile()) == shops(Profile(), None)
    assert shops(veteran, None) != shops(Profile(), None)


def test_play_daily_records_result_and_skips_endless(monkeypatch: pytest.MonkeyPatch) -> None:
    from belote.belatro import main as bmain
    from belote.belatro.ui.history import BelAtroHistoryEntry

    shown: list[list[str]] = []
    monkeypatch.setattr(daily, "_show", lambda lines, reader: shown.append(lines) or True)

    def fake_start(self: bmain.BelAtroGame, reader: object, run: object = None) -> None:
        assert run is not None and run.daily == "2026-11-01"  # type: ignore[attr-defined]
        run.ante_number = 2  # type: ignore[attr-defined]
        run.history.append(  # type: ignore[attr-defined]
            BelAtroHistoryEntry(ante=1, blind_label="Small", target=80, boss_name=None,
                                taker_label="S (NS)", contract="♠", tricks_ns=5, tricks_ew=3,
                                score=321, status="WON", money_delta=3,
                                decl_summary_ns=(), decl_summary_ew=())
        )
        self.run = run  # type: ignore[assignment]

    monkeypatch.setattr(bmain.BelAtroGame, "start", fake_start)
    daily.play_daily(None, DAY)  # type: ignore[arg-type]
    best, attempts = daily.best_for(DAY)
    assert attempts == 1 and best is not None and best.ante == 2 and best.score == 321
    assert any("NEW BEST" in line for line in shown[-1])
