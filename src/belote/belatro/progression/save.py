from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Profile:
    """Persistent player profile storing unlocks and statistics."""

    unlocked_ids: list[str] = field(
        default_factory=lambda: ["le_classique", "le_courageux", "l_econome"]
    )
    stats: dict[str, Any] = field(
        default_factory=lambda: dict.fromkeys(
            ("runs_won", "total_capots", "sans_atout_wins", "tout_atout_wins"), 0
        )
    )

    def is_unlocked(self, item_id: str) -> bool:
        return item_id in self.unlocked_ids

    def unlock(self, item_id: str) -> bool:
        """Returns True if the item was newly unlocked."""
        if item_id not in self.unlocked_ids:
            self.unlocked_ids.append(item_id)
            return True
        return False


class SaveManager:
    """Handles OS-specific persistence of player profiles."""

    def __init__(self, app_name: str = "belatro") -> None:
        self._save_path = self._get_save_path(app_name) / "profile.json"

    def _get_save_path(self, app_name: str) -> Path:
        """Resolve XDG-compliant data path."""
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", "."))
        else:
            xdg = os.environ.get("XDG_DATA_HOME", "")
            base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        path = base / app_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_profile(self, profile: Profile) -> None:
        import dataclasses

        with self._save_path.open("w") as f:
            json.dump(dataclasses.asdict(profile), f, indent=4)

    def load_profile(self) -> Profile:
        try:
            with self._save_path.open() as f:
                data = json.load(f)
            return Profile(
                unlocked_ids=data.get("unlocked_ids", []),
                stats=data.get("stats", {}),
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return Profile()
