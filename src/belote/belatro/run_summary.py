"""3.0.0: append a one-line JSON summary per BelAtro run to a local file.

Useful for the player's own analysis ("which decks reach Ante 8 most often?")
without sending telemetry anywhere. The file lives at
``~/.local/share/belote/run_history.jsonl`` (XDG-compliant) on Linux, or
``%APPDATA%/belote/run_history.jsonl`` on Windows.

Each line is one JSON object so it can be tail-followed or processed with
``jq``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.run_state import BelAtroRun


# Cache the resolved path so we don't re-resolve XDG and re-mkdir on every
# call. The dir-creation side-effect is preserved on the first call only.
_PATH_CACHE: Path | None = None


def _summary_path() -> Path:
    global _PATH_CACHE
    if _PATH_CACHE is not None:
        return _PATH_CACHE
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "."))
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    path = base / "belote"
    path.mkdir(parents=True, exist_ok=True)
    _PATH_CACHE = path / "run_history.jsonl"
    return _PATH_CACHE


def append_summary(run: BelAtroRun, *, won: bool) -> None:
    """Append a one-line summary for the just-ended run.

    Failures (write errors) are swallowed — this is best-effort housekeeping,
    never block the user's exit on it.
    """
    try:
        record = {
            "ts": int(time.time()),
            "deck_id": run.deck_id,
            "ante_reached": run.ante_number,
            "blind_index": run.blind_index,
            "endless": run.endless,
            "endless_offset": run.endless_ante_offset,
            "won": won,
            "joker_count": len(run.jokers),
            "joker_ids": [getattr(j, "id", "?") for j in run.jokers],
            "voucher_count": len(run.vouchers),
            "money": getattr(run.economy, "money", 0)
            if hasattr(run, "economy")
            else 0,
        }
        path = _summary_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        # Logging failure is intentionally silent — telemetry is non-essential.
        pass
