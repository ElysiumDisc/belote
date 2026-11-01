"""scripts/balance.py smoke: the paired simulation runs and is deterministic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "balance.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("belote_balance_script", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_balance_simulation_is_paired_and_deterministic() -> None:
    from belote.belatro.items.registry import register_all_items, registry

    register_all_items()
    bal = _load()
    pool = sorted(registry.jokers)
    args = (["le_capitaine", "le_demon"], pool, 2, 7, 2, 20)
    rows = bal.simulate(*args)
    assert [r["id"] for r in rows] == ["le_demon", "le_capitaine"]  # sorted by Δscore
    assert rows == bal.simulate(*args)
    demon = rows[0]
    assert demon["mean_with"] > demon["mean_without"]
    assert {"delta_pct", "win_with", "win_without", "money_delta"} <= demon.keys()
    table = bal.format_table(rows)
    assert "* Le Capitaine" in table and "Le Démon" in table
