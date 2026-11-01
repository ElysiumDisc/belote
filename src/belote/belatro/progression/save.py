from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class _NewerSchemaError(ValueError):
    """Save file was written by a newer build (schema_version too high)."""


@dataclass
class Profile:
    """Persistent player profile storing unlocks and statistics."""

    unlocked_ids: list[str] = field(
        default_factory=lambda: ["le_classique", "le_courageux", "l_econome"]
    )
    discovered_items: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(
        default_factory=lambda: dict.fromkeys(
            ("runs_won", "total_capots", "sans_atout_wins", "tout_atout_wins"), 0
        )
    )
    # 4.7.0: one-time discoverability flag for the Dix de Der Heist.
    # Set to True the first time the player takes a contract without owning
    # the La Voûte voucher (so the heist prompt has no reward to offer).
    # When set, `UICallbacks.prompt_heist` no longer shows the explainer
    # banner — players who've seen the tip aren't pestered again. Persisted
    # via SaveManager; loaded with a default of False for legacy saves (no
    # SCHEMA_VERSION bump needed, dataclass default kicks in).
    seen_heist_hint: bool = False

    def is_unlocked(self, item_id: str) -> bool:
        return item_id in self.unlocked_ids

    def unlock(self, item_id: str) -> bool:
        """Returns True if the item was newly unlocked."""
        if item_id not in self.unlocked_ids:
            self.unlocked_ids.append(item_id)
            return True
        return False

    def discover(self, item_id: str) -> bool:
        """Add an item to the collection if not already present."""
        if item_id not in self.discovered_items:
            self.discovered_items.append(item_id)
            return True
        return False


class SaveManager:
    """Handles OS-specific persistence of player profiles."""

    def __init__(self, app_name: str = "belote") -> None:
        self._save_path = self._get_save_path(app_name) / "profile.json"
        # Set by load_profile when the file was written by a newer build.
        self._newer_schema = False

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

    def delete_profile(self) -> None:
        """Permanently remove the profile file from disk."""
        if self._save_path.exists():
            self._save_path.unlink()

    SCHEMA_VERSION: int = 1

    def save_profile(self, profile: Profile) -> None:
        import dataclasses
        import tempfile

        if self._newer_schema:
            # The on-disk profile came from a newer build; this session runs
            # on a throwaway default profile and must not clobber it.
            return

        payload = {"schema_version": self.SCHEMA_VERSION, **dataclasses.asdict(profile)}
        # Atomic write: dump to a sibling tmp file, fsync, then os.replace
        # which is atomic on POSIX/NTFS. A crash mid-write leaves the original
        # profile.json intact instead of truncating it to invalid JSON.
        directory = self._save_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(directory), prefix=".profile-", suffix=".json.tmp", delete=False
        ) as tf:
            tmp_path = Path(tf.name)
            json.dump(payload, tf, indent=4)
            tf.flush()
            os.fsync(tf.fileno())
        tmp_path.replace(self._save_path)

    def load_profile(self) -> Profile:
        """Load the profile, never raising on a bad file.

        - Missing file → fresh Profile.
        - Unreadable / non-UTF-8 / invalid JSON / wrong shape or types →
          the bad file is moved to ``profile.json.bak`` and a fresh Profile
          is returned (so the next save doesn't silently destroy evidence).
        - Written by a NEWER build (schema_version too high) → a fresh
          in-memory Profile is returned but the file is left untouched:
          `_newer_schema` is set so `save_profile` refuses to overwrite it.
          Callers (BelAtroGame.__init__, belote/ui/announce.py) therefore
          never see the ValueError `_migrate` raises for that case.
        """
        self._newer_schema = False
        try:
            raw = self._save_path.read_bytes()
        except FileNotFoundError:
            return Profile()
        except OSError:
            return Profile()
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise TypeError(f"profile root must be an object, got {type(data).__name__}")
            data = self._migrate(data)
            return self._profile_from_dict(data)
        except _NewerSchemaError:
            self._newer_schema = True
            return Profile()
        except (UnicodeDecodeError, ValueError, TypeError):
            # json.JSONDecodeError is a ValueError subclass.
            self._quarantine()
            return Profile()

    @staticmethod
    def _profile_from_dict(data: dict[str, Any]) -> Profile:
        """Build a Profile from a migrated save dict, validating types.

        Raises TypeError on a field of the wrong type (e.g. a string where a
        list is expected — `list("abc")` would otherwise load as chars).
        """
        def _str_list(key: str, default: list[str]) -> list[str]:
            if key not in data:
                return default
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise TypeError(f"{key!r} must be a list of strings")
            return list(value)

        stats = data.get("stats", {})
        if not isinstance(stats, dict):
            raise TypeError("'stats' must be an object")
        default = Profile()
        for key in default.stats:  # counters are incremented with `+= 1`
            value = stats.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"stats[{key!r}] must be an integer")
        # When a saved profile is missing `unlocked_ids` (older saves,
        # manual edits, partial writes), fall back to the Profile
        # dataclass default rather than an empty list — otherwise the
        # player loses their starter unlocks on reload.
        return Profile(
            unlocked_ids=_str_list("unlocked_ids", default.unlocked_ids),
            discovered_items=_str_list("discovered_items", []),
            stats={**default.stats, **stats},
            seen_heist_hint=bool(data.get("seen_heist_hint", False)),
        )

    def _quarantine(self) -> None:
        """Move a corrupt profile aside to ``profile.json.bak`` (best-effort)."""
        with contextlib.suppress(OSError):
            self._save_path.replace(self._save_path.with_name(self._save_path.name + ".bak"))

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Upgrade older save dicts to the current schema.

        Profiles written before SCHEMA_VERSION existed have no `schema_version`
        key but are otherwise structurally compatible. New keys with sensible
        defaults can be added here as the schema evolves.

        4.6.6: reject saves written by a *newer* version of the game. Without
        this guard, a forward-incompatible field change (e.g. renaming a stat,
        repurposing a list) would silently load as garbage.
        """
        version = int(data.get("schema_version", 0))  # garbage → ValueError/TypeError
        if version > self.SCHEMA_VERSION:
            raise _NewerSchemaError(
                f"Save file schema_version={version} is newer than this "
                f"build's SCHEMA_VERSION={self.SCHEMA_VERSION}. Upgrade the "
                "game to load this profile."
            )
        # No structural migrations yet — just normalise the version field.
        if version < self.SCHEMA_VERSION:
            data["schema_version"] = self.SCHEMA_VERSION
        return data
