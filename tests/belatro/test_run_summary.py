"""H1 audit fix: run-history JSONL appends are durable.

Pre-3.5.0 `append_summary` wrote a JSON line and let the file's buffer drain
whenever the OS chose to. A crash or power-loss mid-write could leave a
truncated final line that broke downstream `jq` processing.

These tests pin that flush + fsync now run on the happy path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from belote.belatro import run_summary
from belote.belatro.core.run_state import BelAtroRun


@pytest.fixture
def _isolated_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the module-cached summary path to a temp file per test."""
    target = tmp_path / "run_history.jsonl"
    monkeypatch.setattr(run_summary, "_PATH_CACHE", target)
    return target


def test_append_summary_calls_flush_and_fsync(
    _isolated_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fsync_calls: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: fsync_calls.append(fd) or real_fsync(fd))

    run_summary.append_summary(BelAtroRun(), won=True)

    assert len(fsync_calls) == 1, "fsync must be called exactly once per append"


def test_append_summary_writes_one_jsonl_line(_isolated_path: Path) -> None:
    run_summary.append_summary(BelAtroRun(), won=True)
    run_summary.append_summary(BelAtroRun(), won=False)

    lines = _isolated_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        # Each line must be valid JSON on its own (truncation regression).
        record: dict[str, Any] = json.loads(line)
        assert "ts" in record
        assert "deck_id" in record
        assert "won" in record


def test_append_summary_swallows_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """The function is best-effort housekeeping — an OSError must not propagate."""

    def _raising_path() -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(run_summary, "_summary_path", _raising_path)
    # Should not raise:
    run_summary.append_summary(BelAtroRun(), won=True)
