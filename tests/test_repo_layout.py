"""Repository-layout invariants that tooling silently depends on."""

from __future__ import annotations

from pathlib import Path


def test_no_src_package_marker() -> None:
    """A `src/__init__.py` makes mypy name modules `src.belote.*`, so every
    absolute `from belote.… import` silently resolved to Any (pre-4.10.0 that
    hid 9 real type errors, including the BelAtro Sans Atout bid bug)."""
    assert not (Path(__file__).resolve().parents[1] / "src" / "__init__.py").exists()


def test_core_never_imports_belatro() -> None:
    """BelAtro is an expansion: the core game may not import it (at module
    level or inside functions). Only the composition root `belote/main.py`
    wires it in, through `belote.belatro.integration`."""
    import ast

    src = Path(__file__).resolve().parents[1] / "src" / "belote"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        rel = path.relative_to(src)
        if rel.parts[0] == "belatro" or rel == Path("main.py"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [mod] if node.level == 0 else [("." * node.level) + mod]
            if any("belatro" in n for n in names):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_core_state_has_no_expansion_fields() -> None:
    """Expansion data lives on a GameState subclass, not on the core state."""
    from dataclasses import fields

    from belote.game import GameState

    names = {f.name for f in fields(GameState)}
    assert not names & {"_joker_state", "_chips", "_mult", "_bonus_money", "boss_modifiers"}
